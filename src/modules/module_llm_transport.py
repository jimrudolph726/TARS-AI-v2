"""Reliable HTTP transport and request coordination for LLM calls."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

import requests


class LLMTransportError(RuntimeError):
    """Base class for failures produced by the LLM transport."""


class LLMRequestTimeout(LLMTransportError):
    """The provider exceeded a configured network or total deadline."""


class LLMRequestCancelled(LLMTransportError):
    """The result is no longer relevant to the active conversation."""


@dataclass(frozen=True)
class TransportSettings:
    connect_timeout: float = 10.0
    read_timeout: float = 45.0
    total_timeout: float = 120.0
    max_retries: int = 1
    retry_backoff: float = 0.5

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> "TransportSettings":
        """Create bounded transport settings from the optional LLM config."""

        def _float(name: str, default: float, minimum: float, maximum: float) -> float:
            try:
                value = float(config.get(name, default))
            except (TypeError, ValueError):
                value = default
            return max(minimum, min(maximum, value))

        try:
            retries = int(config.get("max_retries", cls.max_retries))
        except (TypeError, ValueError):
            retries = cls.max_retries

        return cls(
            connect_timeout=_float("connect_timeout", cls.connect_timeout, 1.0, 60.0),
            read_timeout=_float("read_timeout", cls.read_timeout, 2.0, 180.0),
            total_timeout=_float("total_timeout", cls.total_timeout, 5.0, 600.0),
            max_retries=max(0, min(3, retries)),
            retry_backoff=_float("retry_backoff", cls.retry_backoff, 0.0, 10.0),
        )


@dataclass
class RequestTicket:
    request_id: int
    source: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    finished_event: threading.Event = field(default_factory=threading.Event)
    cancel_reason: str = ""
    _response: object | None = field(default=None, init=False, repr=False)
    _response_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def attach_response(self, response: object) -> None:
        with self._response_lock:
            self._response = response
            cancelled = self.cancel_event.is_set()
        if cancelled:
            self._close_response(response)
            self.raise_if_cancelled()

    def detach_response(self, response: object) -> None:
        with self._response_lock:
            if self._response is response:
                self._response = None

    def cancel(self, reason: str) -> None:
        self.cancel_reason = reason
        self.cancel_event.set()
        with self._response_lock:
            response = self._response
        if response is not None:
            self._close_response(response)

    def raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise LLMRequestCancelled(self.cancel_reason or "LLM request cancelled")

    @staticmethod
    def _close_response(response: object) -> None:
        try:
            response.close()
        except Exception:
            pass


class LLMRequestCoordinator:
    """Ensures the newest voice turn owns the voice response stream.

    Web, Discord, reminder, and other background requests remain independent.
    A normal voice request supersedes an unfinished speculative/preemptive one.
    """

    _VOICE_SOURCES = frozenset({"voice", "preemptive"})

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_request_id = 1
        self._active_voice: RequestTicket | None = None

    def begin(self, source: str) -> RequestTicket:
        normalized = str(source or "background").strip().lower()
        with self._lock:
            ticket = RequestTicket(self._next_request_id, normalized)
            self._next_request_id += 1

            if normalized not in self._VOICE_SOURCES:
                return ticket

            active = self._active_voice
            if normalized == "preemptive" and active is not None:
                ticket.cancel("another voice request is already active")
                return ticket

            self._active_voice = ticket

        if active is not None:
            active.cancel(f"superseded by voice request {ticket.request_id}")
        return ticket

    def finish(self, ticket: RequestTicket) -> None:
        ticket.finished_event.set()
        with self._lock:
            if self._active_voice is ticket:
                self._active_voice = None

    def is_current(self, ticket: RequestTicket) -> bool:
        if ticket.source not in self._VOICE_SOURCES:
            return not ticket.cancel_event.is_set()
        with self._lock:
            return self._active_voice is ticket and not ticket.cancel_event.is_set()

    def cancel_preemptive(
        self,
        reason: str = "preemptive transcript invalidated",
    ) -> bool:
        with self._lock:
            active = self._active_voice
        if active is None or active.source != "preemptive":
            return False
        active.cancel(reason)
        return True


def _is_retryable(error: requests.RequestException) -> bool:
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(error, requests.HTTPError):
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        return status in {408, 425, 429, 500, 502, 503, 504}
    return False


def _remaining_timeout(deadline: float, configured: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LLMRequestTimeout("LLM request exceeded its total deadline")
    return max(0.1, min(configured, remaining))


def _retry_wait(ticket: RequestTicket, delay: float) -> None:
    if delay <= 0:
        ticket.raise_if_cancelled()
        return
    if ticket.cancel_event.wait(delay):
        ticket.raise_if_cancelled()


def stream_chat_completion(
    session: requests.Session,
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, object],
    settings: TransportSettings,
    ticket: RequestTicket,
    *,
    on_token: Callable[[str], None] | None = None,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> str:
    """Return text from an OpenAI-compatible SSE response.

    Retries occur only before a content token is received. Retrying a partial
    stream could make TARS speak the beginning of an answer twice.
    """

    deadline = time.monotonic() + settings.total_timeout
    last_error: Exception | None = None

    for attempt in range(settings.max_retries + 1):
        ticket.raise_if_cancelled()
        response = None
        content_parts: list[str] = []
        try:
            connect_timeout = _remaining_timeout(deadline, settings.connect_timeout)
            read_timeout = _remaining_timeout(deadline, settings.read_timeout)
            response = session.post(
                url,
                headers=dict(headers),
                json=dict(payload),
                stream=True,
                timeout=(connect_timeout, read_timeout),
            )
            ticket.attach_response(response)
            response.raise_for_status()

            for line in response.iter_lines():
                ticket.raise_if_cancelled()
                if time.monotonic() >= deadline:
                    raise LLMRequestTimeout("LLM stream exceeded its total deadline")
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    token = chunk["choices"][0]["delta"].get("content", "")
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue
                if token:
                    content_parts.append(token)
                    if on_token is not None:
                        on_token(token)
            ticket.raise_if_cancelled()
            return "".join(content_parts).strip()
        except LLMRequestCancelled:
            raise
        except LLMRequestTimeout:
            raise
        except requests.Timeout as exc:
            last_error = LLMRequestTimeout(f"LLM network timeout: {exc}")
            retryable = True
        except requests.RequestException as exc:
            last_error = exc
            retryable = _is_retryable(exc)
        finally:
            if response is not None:
                ticket.detach_response(response)
                RequestTicket._close_response(response)

        if content_parts or not retryable or attempt >= settings.max_retries:
            if isinstance(last_error, Exception):
                raise last_error
            raise LLMTransportError("LLM stream failed without an error")

        if on_retry is not None and last_error is not None:
            on_retry(attempt + 1, last_error)
        retry_delay = settings.retry_backoff * (2**attempt)
        if retry_delay > 0:
            retry_delay = _remaining_timeout(deadline, retry_delay)
        _retry_wait(ticket, retry_delay)

    raise last_error or LLMTransportError("LLM stream failed")


def post_json_completion(
    session: requests.Session,
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, object],
    settings: TransportSettings,
    ticket: RequestTicket,
    *,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> object:
    """POST a non-streaming completion with bounded transient retries."""

    deadline = time.monotonic() + settings.total_timeout
    last_error: Exception | None = None

    for attempt in range(settings.max_retries + 1):
        ticket.raise_if_cancelled()
        response = None
        try:
            connect_timeout = _remaining_timeout(deadline, settings.connect_timeout)
            read_timeout = _remaining_timeout(deadline, settings.read_timeout)
            response = session.post(
                url,
                headers=dict(headers),
                json=dict(payload),
                timeout=(connect_timeout, read_timeout),
            )
            ticket.attach_response(response)
            response.raise_for_status()
            ticket.raise_if_cancelled()
            return response.json()
        except LLMRequestCancelled:
            raise
        except requests.Timeout as exc:
            last_error = LLMRequestTimeout(f"LLM network timeout: {exc}")
            retryable = True
        except requests.RequestException as exc:
            last_error = exc
            retryable = _is_retryable(exc)
        finally:
            if response is not None:
                ticket.detach_response(response)
                RequestTicket._close_response(response)

        if not retryable or attempt >= settings.max_retries:
            if isinstance(last_error, Exception):
                raise last_error
            raise LLMTransportError("LLM request failed without an error")

        if on_retry is not None and last_error is not None:
            on_retry(attempt + 1, last_error)
        retry_delay = settings.retry_backoff * (2**attempt)
        if retry_delay > 0:
            retry_delay = _remaining_timeout(deadline, retry_delay)
        _retry_wait(ticket, retry_delay)

    raise last_error or LLMTransportError("LLM request failed")
