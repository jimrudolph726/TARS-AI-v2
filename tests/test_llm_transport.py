"""Tests for LLM timeouts, retries, and voice-request coordination."""

from __future__ import annotations

import json
import unittest

import requests

from modules.module_llm_transport import (
    LLMRequestCancelled,
    LLMRequestCoordinator,
    LLMRequestTimeout,
    TransportSettings,
    post_json_completion,
    stream_chat_completion,
)


def _sse(content: str) -> bytes:
    payload = {"choices": [{"delta": {"content": content}}]}
    return f"data: {json.dumps(payload)}".encode()


class FakeResponse:
    def __init__(self, *, lines=(), status=200, json_data=None, stream_error=None):
        self.lines = list(lines)
        self.status_code = status
        self.json_data = json_data
        self.stream_error = stream_error
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def iter_lines(self):
        yield from self.lines
        if self.stream_error is not None:
            raise self.stream_error

    def json(self):
        return self.json_data

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class LLMTransportTests(unittest.TestCase):
    def setUp(self):
        self.settings = TransportSettings(
            connect_timeout=1,
            read_timeout=2,
            total_timeout=5,
            max_retries=1,
            retry_backoff=0,
        )
        self.coordinator = LLMRequestCoordinator()

    def stream(self, session, ticket, **kwargs):
        return stream_chat_completion(
            session,
            "https://example.invalid/chat",
            {"Authorization": "Bearer test"},
            {"stream": True},
            self.settings,
            ticket,
            **kwargs,
        )

    def test_network_timeout_is_bounded_and_retried_once(self):
        session = FakeSession(requests.Timeout("first"), requests.Timeout("second"))
        ticket = self.coordinator.begin("webui")

        with self.assertRaises(LLMRequestTimeout):
            self.stream(session, ticket)

        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0][1]["timeout"], (1, 2))

    def test_transient_server_error_retries_before_any_tokens(self):
        unavailable = FakeResponse(status=503)
        success = FakeResponse(lines=[_sse("Ready."), b"data: [DONE]"])
        session = FakeSession(unavailable, success)
        ticket = self.coordinator.begin("webui")

        result = self.stream(session, ticket)

        self.assertEqual(result, "Ready.")
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(unavailable.closed)
        self.assertTrue(success.closed)

    def test_permanent_client_error_is_not_retried(self):
        bad_request = FakeResponse(status=400)
        session = FakeSession(bad_request)
        ticket = self.coordinator.begin("webui")

        with self.assertRaises(requests.HTTPError):
            self.stream(session, ticket)

        self.assertEqual(len(session.calls), 1)
        self.assertTrue(bad_request.closed)

    def test_partial_stream_is_never_retried_or_spoken_twice(self):
        partial = FakeResponse(
            lines=[_sse("Partial")],
            stream_error=requests.ConnectionError("stream dropped"),
        )
        unused = FakeResponse(lines=[_sse("Duplicate")])
        session = FakeSession(partial, unused)
        ticket = self.coordinator.begin("webui")
        heard = []

        with self.assertRaises(requests.ConnectionError):
            self.stream(session, ticket, on_token=heard.append)

        self.assertEqual(heard, ["Partial"])
        self.assertEqual(len(session.calls), 1)
        self.assertTrue(partial.closed)

    def test_new_voice_request_cancels_and_closes_preemptive_request(self):
        preemptive = self.coordinator.begin("preemptive")
        response = FakeResponse()
        preemptive.attach_response(response)

        voice = self.coordinator.begin("voice")

        self.assertTrue(preemptive.cancel_event.is_set())
        self.assertTrue(response.closed)
        self.assertTrue(self.coordinator.is_current(voice))
        with self.assertRaises(LLMRequestCancelled):
            preemptive.raise_if_cancelled()

    def test_second_preemptive_request_cannot_replace_active_voice(self):
        voice = self.coordinator.begin("voice")
        speculative = self.coordinator.begin("preemptive")

        self.assertTrue(speculative.cancel_event.is_set())
        self.assertTrue(self.coordinator.is_current(voice))

    def test_nonstreaming_request_retries_and_closes_responses(self):
        unavailable = FakeResponse(status=429)
        success = FakeResponse(json_data={"choices": []})
        session = FakeSession(unavailable, success)
        ticket = self.coordinator.begin("followup")

        result = post_json_completion(
            session,
            "https://example.invalid/chat",
            {},
            {"stream": False},
            self.settings,
            ticket,
        )

        self.assertEqual(result, {"choices": []})
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(unavailable.closed)
        self.assertTrue(success.closed)


if __name__ == "__main__":
    unittest.main()
