"""Wake-word matching and non-blocking notification helpers."""

from __future__ import annotations

import threading
from difflib import SequenceMatcher
from urllib.request import urlopen


def fuzzy_wake_word_match(transcript: str, wake_word: str, threshold: float = 0.6) -> bool:
    wake_words = wake_word.split()
    transcript_words = transcript.split()
    if len(transcript_words) < len(wake_words):
        return False
    for index in range(len(transcript_words) - len(wake_words) + 1):
        window = transcript_words[index:index + len(wake_words)]
        if all(
            SequenceMatcher(None, heard, expected).ratio() >= threshold
            for heard, expected in zip(window, wake_words)
        ):
            return True
    return False


def fire_and_forget_get(url: str) -> None:
    def notify() -> None:
        # Keep the wake-word matching module importable in hardware-free test
        # and recovery environments. A missing/broken WebUI notification must
        # never take down STT.
        try:
            with urlopen(url, timeout=1):
                pass
        except Exception:
            pass

    threading.Thread(
        target=notify,
        name="stt-notify",
        daemon=True,
    ).start()
