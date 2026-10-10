"""Pure gait profiles shared by movement code and diagnostic interfaces."""

from __future__ import annotations


def body_swing_profile(direction: str, arms_present: bool, fast: bool = False):
    """Return the configured body-swing targets and phase timings.

    Percentages use the servo module's convention: smaller height values raise
    the chassis and smaller forward/back values move toward the front.
    """
    if direction not in ("forward", "backward"):
        raise ValueError(f"Unsupported gait direction: {direction}")

    if arms_present:
        stride = 30
        raised_height, planted_height, unloaded_height = 32, 78, 16
    else:
        stride = 26
        raised_height, planted_height, unloaded_height = 38, 72, 22

    stride_target = 50 - stride if direction == "forward" else 50 + stride
    if fast:
        timings = (0.22, 0.28, 0.36, 0.38, 0.48, 0.30, 0.26)
    else:
        timings = (0.30, 0.42, 0.48, 0.54, 0.66, 0.40, 0.34)
    return stride_target, raised_height, planted_height, unloaded_height, timings


def body_swing_diagnostic_phases(direction: str, arms_present: bool) -> list[dict]:
    """Build manually triggered poses that expose each support-transfer step."""
    (
        stride_target,
        raised_height,
        planted_height,
        unloaded_height,
        timings,
    ) = body_swing_profile(direction, arms_present, fast=False)
    raise_time, swing_time, lower_time, unload_time, follow_time, replant_time, neutral_time = timings

    # Move only one quarter of the horizontal recovery before replanting. This
    # exposes whether TARS loses balance immediately on leg translation while
    # keeping the diagnostic step deliberately conservative.
    partial_target = round(stride_target + (50 - stride_target) * 0.25)
    direction_word = "forward" if direction == "forward" else "backward"

    return [
        {
            "index": 1,
            "key": "raise",
            "name": "RAISE BODY",
            "description": "Raise vertically; legs remain centered.",
            "pose": (raised_height, raised_height, 50, 50),
            "duration": raise_time,
        },
        {
            "index": 2,
            "key": "swing",
            "name": "SWING BODY",
            "description": f"Swing {direction_word}; hold raised height.",
            "pose": (raised_height, raised_height, stride_target, stride_target),
            "duration": swing_time,
        },
        {
            "index": 3,
            "key": "lower",
            "name": "LOWER + SETTLE",
            "description": "Lower vertically onto the chassis support edge.",
            "pose": (planted_height, planted_height, stride_target, stride_target),
            "duration": lower_time,
        },
        {
            "index": 4,
            "key": "lift",
            "name": "LIFT LEGS",
            "description": "Retract both feet fully before translating them.",
            "pose": (unloaded_height, unloaded_height, stride_target, stride_target),
            "duration": unload_time,
        },
        {
            "index": 5,
            "key": "partial_follow",
            "name": "PARTIAL FOLLOW",
            "description": "Move raised legs 25% toward the body.",
            "pose": (unloaded_height, unloaded_height, partial_target, partial_target),
            "duration": max(0.30, follow_time * 0.35),
        },
        {
            "index": 6,
            "key": "replant",
            "name": "REPLANT",
            "description": "Lower feet at the partial-return position.",
            "pose": (planted_height, planted_height, partial_target, partial_target),
            "duration": replant_time,
        },
        {
            "index": 7,
            "key": "finish_legs",
            "name": "FINISH LEGS",
            "description": "Bring planted legs underneath the body.",
            "pose": (planted_height, planted_height, 50, 50),
            "duration": max(0.36, follow_time * 0.65),
        },
        {
            "index": 8,
            "key": "finish_neutral",
            "name": "NEUTRAL BODY",
            "description": "Return body height to neutral and finish.",
            "pose": (50, 50, 50, 50),
            "duration": neutral_time,
        },
    ]
