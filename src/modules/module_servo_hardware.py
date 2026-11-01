"""Low-level, UI-independent PCA9685 hardware operations."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import nullcontext


def describe_hardware_error(exc: Exception) -> str:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 121:
        return "I2C remote I/O error; check PCA9685 power, ground, SDA, and SCL wiring"
    return str(exc)


def probe_controller(controller, io_lock=None, probe_channel: int = 15) -> tuple[bool, Exception | None]:
    if controller is None:
        return False, None
    try:
        context = io_lock if io_lock is not None else nullcontext()
        with context:
            controller.channels[probe_channel].duty_cycle = 0
        return True, None
    except Exception as exc:
        return False, exc


def disable_controller_outputs(
    controller,
    *,
    io_lock=None,
    attempts: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
    on_error: Callable[[int, Exception], None] | None = None,
) -> list[int]:
    """Release all outputs, retrying only failed channels."""
    if controller is None:
        return []
    pending = list(range(16))
    last_errors: dict[int, Exception] = {}
    context = io_lock if io_lock is not None else nullcontext()
    with context:
        for attempt in range(max(1, int(attempts))):
            failed = []
            for channel in pending:
                try:
                    controller.channels[channel].duty_cycle = 0
                    last_errors.pop(channel, None)
                except Exception as exc:
                    failed.append(channel)
                    last_errors[channel] = exc
            pending = failed
            if not pending:
                return []
            if attempt < attempts - 1:
                sleep_fn(0.03 * (attempt + 1))
    if on_error is not None:
        for channel in pending:
            on_error(channel, last_errors[channel])
    return pending


def close_quietly(device) -> None:
    if device is None:
        return
    try:
        device.deinit()
    except Exception:
        pass
