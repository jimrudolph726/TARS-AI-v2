"""Toolkit-neutral image presentation bridge.

The active on-device UI registers a presenter. Skills can then display an image
without importing Qt, Pygame, or a specific application entry point.
"""

from __future__ import annotations

import threading
from collections.abc import Callable


_lock = threading.RLock()
_presenter: Callable[[str, int], None] | None = None


def register_image_presenter(presenter: Callable[[str, int], None]) -> None:
    global _presenter
    with _lock:
        _presenter = presenter


def unregister_image_presenter(presenter: Callable[[str, int], None]) -> None:
    global _presenter
    with _lock:
        if _presenter == presenter:
            _presenter = None


def present_image(path: str, duration: int = 8) -> bool:
    with _lock:
        presenter = _presenter
    if presenter is None:
        return False
    presenter(str(path), int(duration))
    return True
