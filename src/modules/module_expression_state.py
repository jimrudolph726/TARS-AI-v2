"""Toolkit-neutral expression state shared by QML and the WebUI."""

from __future__ import annotations

import threading
from enum import Enum


class Mood(str, Enum):
    NEUTRAL = "NEUTRAL"
    HAPPY = "HAPPY"
    SAD = "SAD"
    ANGRY = "ANGRY"
    EXCITED = "EXCITED"
    AFRAID = "AFRAID"
    SIDEEYE_LEFT = "SIDEEYE_LEFT"
    SIDEEYE_RIGHT = "SIDEEYE_RIGHT"
    SLEEPY = "SLEEPY"
    CONFUSED = "CONFUSED"
    SURPRISED = "SURPRISED"
    DISGUSTED = "DISGUSTED"
    LOVE = "LOVE"
    SHY = "SHY"
    ANNOYED = "ANNOYED"
    CURIOUS = "CURIOUS"


_lock = threading.RLock()
_mood = Mood.NEUTRAL


def set_mood(mood: Mood | str) -> Mood:
    """Set and return the current eye mood."""
    global _mood
    requested = mood if isinstance(mood, Mood) else Mood[str(mood).strip().upper()]
    with _lock:
        _mood = requested
        return _mood


def get_mood() -> Mood:
    with _lock:
        return _mood
