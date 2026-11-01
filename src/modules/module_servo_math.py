"""Pure servo conversion, envelope, and interpolation calculations."""

from __future__ import annotations

import math
from numbers import Integral, Real


def pulse_to_duty_cycle(pulse_value: int | float, maximum_pulse: int = 600) -> int:
    pulse_us = 500 + (float(pulse_value) / maximum_pulse) * 2000
    return int((pulse_us / 20000.0) * 65535)


def channel_bounds(
    channel: int,
    ranges: dict[int, tuple[int, ...]],
    controller_minimum: int = 10,
    controller_maximum: int = 600,
) -> tuple[int, int] | None:
    values = ranges.get(channel)
    if values is None:
        return None
    return (
        max(controller_minimum, min(values)),
        min(controller_maximum, max(values)),
    )


def validate_write(
    channel,
    pwm_value,
    bounds: tuple[int, int] | None,
    current_value=None,
    *,
    controller_minimum: int = 10,
    controller_maximum: int = 600,
    enforce_calibrated_bounds: bool = True,
) -> tuple[tuple[int, int] | None, str | None]:
    """Normalize a PWM request or return a user-facing rejection reason."""
    if isinstance(channel, bool) or not isinstance(channel, Integral):
        return None, f"invalid channel {channel!r}"
    channel = int(channel)
    if bounds is None:
        return None, f"unassigned channel {channel}; TARS servo channels are 0-9"
    if isinstance(pwm_value, bool) or not isinstance(pwm_value, Real):
        return None, f"non-numeric PWM value {pwm_value!r} on channel {channel}"
    numeric_value = float(pwm_value)
    if not math.isfinite(numeric_value) or not numeric_value.is_integer():
        return None, f"non-integer PWM value {pwm_value!r} on channel {channel}"
    pwm_value = int(numeric_value)
    if not controller_minimum <= pwm_value <= controller_maximum:
        return None, (
            f"unsafe PWM value {pwm_value} on channel {channel}; controller range "
            f"is {controller_minimum}-{controller_maximum}"
        )
    if enforce_calibrated_bounds:
        minimum, maximum = bounds
        recovering_low = (
            isinstance(current_value, Real)
            and current_value < minimum
            and current_value < pwm_value < minimum
        )
        recovering_high = (
            isinstance(current_value, Real)
            and current_value > maximum
            and maximum < pwm_value < current_value
        )
        if not minimum <= pwm_value <= maximum and not (recovering_low or recovering_high):
            return None, (
                f"PWM value {pwm_value} on channel {channel}; calibrated range "
                f"is {minimum}-{maximum}"
            )
    return (channel, pwm_value), None


def percentage_to_value(percent, minimum: int, maximum: int, *, hold=False):
    if percent is None or percent == 0:
        return None
    if hold and percent == -1:
        return -1
    normalized = (float(percent) - 1.0) / 99.0
    return int(round(minimum + (maximum - minimum) * normalized))


def eased_progress(linear_progress: float, easing_strength: float) -> float:
    linear = max(0.0, min(1.0, float(linear_progress)))
    easing = max(0.0, min(1.0, float(easing_strength)))
    smooth = linear * linear * (3.0 - 2.0 * linear)
    return linear * (1.0 - easing) + smooth * easing


def synchronized_duration(max_distance: int, speed_factor: float) -> float:
    speed = max(0.05, min(1.0, float(speed_factor)))
    ticks_per_second = 70.0 + 230.0 * speed
    return max(0.10, int(max_distance) / ticks_per_second)
