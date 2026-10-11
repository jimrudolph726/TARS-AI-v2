"""Small synchronous client for OpenAI realtime transcription sessions.

TARS owns microphone capture and end-of-turn detection.  This client only
opens a transcription WebSocket, streams 24 kHz PCM16 audio, commits the
finished turn, and returns the final transcript.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Callable, Iterable, Optional
from urllib.parse import quote

import numpy as np

try:
    import websocket
except ImportError:  # Optional so the local STT fallback can still run.
    websocket = None


class OpenAILiveTranscriptionError(RuntimeError):
    """Raised when a realtime transcription session cannot complete."""


def _pcm16_16k_to_24k(samples: np.ndarray) -> bytes:
    """Resample mono PCM16 from 16 kHz to the API's required 24 kHz."""
    source = np.asarray(samples, dtype=np.int16).reshape(-1)
    if source.size == 0:
        return b""

    try:
        from scipy.signal import resample_poly

        converted = resample_poly(source.astype(np.float32), 3, 2)
    except ImportError:
        # scipy is installed by TARS, but retain a lightweight fallback for
        # development environments and incomplete installations.
        target_length = max(1, int(round(source.size * 1.5)))
        old_positions = np.arange(source.size, dtype=np.float64)
        new_positions = np.linspace(0, source.size - 1, target_length)
        converted = np.interp(new_positions, old_positions, source)

    return np.clip(np.rint(converted), -32768, 32767).astype("<i2").tobytes()


class OpenAILiveTranscriber:
    """One OpenAI realtime transcription session for one user utterance."""

    DEFAULT_URL = "wss://api.openai.com/v1/realtime?model={model}"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-live-transcribe",
        delay: str = "low",
        language: str = "en",
        prompt: str = "",
        keywords: Optional[Iterable[str]] = None,
        connect_timeout: float = 4.0,
        response_timeout: float = 12.0,
        websocket_factory: Optional[Callable] = None,
    ):
        self.api_key = (api_key or "").strip()
        self.model = model.strip() or "gpt-live-transcribe"
        self.delay = delay if delay in {"minimal", "low", "medium", "high", "xhigh"} else "low"
        self.language = (language or "en").strip().lower()
        self.prompt = (prompt or "").strip()
        self.keywords = self._clean_keywords(keywords or [])
        self.connect_timeout = max(1.0, float(connect_timeout))
        self.response_timeout = max(2.0, float(response_timeout))
        self._websocket_factory = websocket_factory
        self._ws = None
        self._audio_messages = 0

    @staticmethod
    def _clean_keywords(keywords: Iterable[str]):
        cleaned = []
        seen = set()
        for keyword in keywords:
            value = str(keyword).replace("\r", " ").replace("\n", " ").strip()
            if not value or "<" in value or ">" in value:
                continue
            marker = value.casefold()
            if marker not in seen:
                seen.add(marker)
                cleaned.append(value)
        return cleaned

    @staticmethod
    def dependency_available() -> bool:
        return websocket is not None and hasattr(websocket, "create_connection")

    def connect(self) -> None:
        if not self.api_key:
            raise OpenAILiveTranscriptionError("OPENAI_API_KEY is not configured")

        factory = self._websocket_factory
        if factory is None:
            if not self.dependency_available():
                raise OpenAILiveTranscriptionError(
                    "websocket-client is not installed (pip install websocket-client)"
                )
            factory = websocket.create_connection

        url = self.DEFAULT_URL.format(model=quote(self.model, safe="-._"))
        try:
            self._ws = factory(
                url,
                header=[f"Authorization: Bearer {self.api_key}"],
                timeout=self.connect_timeout,
                enable_multithread=True,
            )
            self._send(self._session_update())
        except Exception as exc:
            self.close()
            raise OpenAILiveTranscriptionError(f"connection failed: {exc}") from exc

    def _session_update(self) -> dict:
        transcription = {
            "model": self.model,
            "delay": self.delay,
        }
        if self.prompt:
            transcription["prompt"] = self.prompt
        if self.keywords:
            transcription["keywords"] = self.keywords
        if self.language:
            transcription["languages"] = [self.language]

        return {
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "transcription": transcription,
                        "turn_detection": None,
                    }
                },
            },
        }

    def send_pcm16_16k(self, samples: np.ndarray) -> None:
        if self._ws is None:
            raise OpenAILiveTranscriptionError("transcription session is not connected")
        audio = _pcm16_16k_to_24k(samples)
        if not audio:
            return
        self._send({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio).decode("ascii"),
        })
        self._audio_messages += 1

    def commit_and_wait(self) -> str:
        if self._ws is None:
            raise OpenAILiveTranscriptionError("transcription session is not connected")
        if self._audio_messages == 0:
            raise OpenAILiveTranscriptionError("no audio was sent")

        self._send({"type": "input_audio_buffer.commit"})
        deadline = time.monotonic() + self.response_timeout
        transcript_deltas = []

        while time.monotonic() < deadline:
            remaining = max(0.1, deadline - time.monotonic())
            try:
                self._ws.settimeout(min(1.0, remaining))
                raw = self._ws.recv()
            except Exception as exc:
                timeout_type = getattr(websocket, "WebSocketTimeoutException", ()) if websocket else ()
                if timeout_type and isinstance(exc, timeout_type):
                    continue
                raise OpenAILiveTranscriptionError(f"receive failed: {exc}") from exc

            if not raw:
                continue
            try:
                event = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue

            event_type = event.get("type", "")
            if event_type == "conversation.item.input_audio_transcription.delta":
                transcript_deltas.append(event.get("delta", ""))
            elif event_type == "conversation.item.input_audio_transcription.completed":
                return (event.get("transcript") or "".join(transcript_deltas)).strip()
            elif event_type == "error":
                error = event.get("error", {})
                detail = error.get("message") if isinstance(error, dict) else str(error)
                raise OpenAILiveTranscriptionError(detail or "OpenAI returned an unknown error")

        raise OpenAILiveTranscriptionError(
            f"timed out after {self.response_timeout:.1f}s waiting for the final transcript"
        )

    def _send(self, event: dict) -> None:
        try:
            self._ws.send(json.dumps(event, separators=(",", ":")))
        except Exception as exc:
            raise OpenAILiveTranscriptionError(f"send failed: {exc}") from exc

    def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

