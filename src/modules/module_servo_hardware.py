"""Low-level, UI-independent PCA9685 hardware operations."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import nullcontext


class UnsafeControllerFrequency(RuntimeError):
    """Raised when a PCA9685 responds but is no longer generating 50 Hz PWM."""


def describe_hardware_error(exc: Exception) -> str:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 121:
        return "I2C remote I/O error; check PCA9685 power, ground, SDA, and SCL wiring"
    return str(exc)


def controller_frequency(
    controller,
    expected_frequency: float,
    tolerance: float,
) -> float:
    """Read and validate the PCA9685 frequency after a possible power reset."""
    actual = float(controller.frequency)
    if abs(actual - float(expected_frequency)) > float(tolerance):
        raise UnsafeControllerFrequency(
            f"PCA9685 PWM frequency changed to {actual:.2f} Hz; "
            f"expected {float(expected_frequency):.2f} Hz"
        )
    return actual


def probe_controller(
    controller,
    io_lock=None,
    probe_channel: int = 15,
    *,
    expected_frequency: float | None = None,
    frequency_tolerance: float = 2.0,
) -> tuple[bool, Exception | None]:
    if controller is None:
        return False, None
    try:
        context = io_lock if io_lock is not None else nullcontext()
        with context:
            controller.channels[probe_channel].duty_cycle = 0
            if expected_frequency is not None:
                controller_frequency(
                    controller,
                    expected_frequency,
                    frequency_tolerance,
                )
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
