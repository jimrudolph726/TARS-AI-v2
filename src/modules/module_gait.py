"""Pure gait profiles shared by movement code and diagnostic interfaces."""

from __future__ import annotations


def body_swing_profile(direction: str, arms_present: bool, fast: bool = False):
    """Return targets and timings for a chassis-supported body-swing gait.

    Percentages use the servo module's convention: smaller height values raise
    the chassis and smaller forward/back values move toward the front.

    ``stride_target`` positions the raised chassis. ``support_target`` then
    rotates farther in the direction of travel while the chassis is lowered,
    transferring its weight from the feet to the chassis support edge.
    ``unload_target`` eases that rotation back slightly as the unloaded feet
    retract, matching the support-transfer geometry of the original gait.
    """
    if direction not in ("forward", "backward"):
        raise ValueError(f"Unsupported gait direction: {direction}")

    if arms_present:
        stride = 30
        raised_height, planted_height, unloaded_height = 32, 78, 16
        support_forward, unload_forward = 8, 17
    else:
        stride = 26
        raised_height, planted_height, unloaded_height = 38, 72, 22
        support_forward, unload_forward = 18, 28

    stride_target = 50 - stride if direction == "forward" else 50 + stride
    support_target = support_forward if direction == "forward" else 100 - support_forward
    unload_target = unload_forward if direction == "forward" else 100 - unload_forward
    if fast:
        timings = (0.22, 0.28, 0.36, 0.28, 0.40, 0.48, 0.34, 0.26)
    else:
        timings = (0.30, 0.42, 0.48, 0.40, 0.58, 0.66, 0.46, 0.34)
    return {
        "stride_target": stride_target,
        "support_target": support_target,
        "unload_target": unload_target,
        "raised_height": raised_height,
        "planted_height": planted_height,
        "unloaded_height": unloaded_height,
        "timings": timings,
    }


def body_swing_diagnostic_phases(direction: str, arms_present: bool) -> list[dict]:
    """Build manually triggered poses that expose each support-transfer step."""
    profile = body_swing_profile(direction, arms_present, fast=False)
    stride_target = profile["stride_target"]
    support_target = profile["support_target"]
    unload_target = profile["unload_target"]
    raised_height = profile["raised_height"]
    planted_height = profile["planted_height"]
    unloaded_height = profile["unloaded_height"]
    (
        raise_time, swing_time, lower_time, transfer_time, unload_time,
        follow_time, replant_time, neutral_time,
    ) = profile["timings"]

    # Split the unloaded leg recovery so the diagnostic can reveal whether
    # instability begins as soon as the feet start following the chassis.
    partial_target = round(unload_target + (50 - unload_target) * 0.25)
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
            "key": "support_transfer",
            "name": "ROLL ONTO BODY",
            "description": "Rotate farther and transfer weight from feet to chassis.",
            "pose": (planted_height, planted_height, support_target, support_target),
            "duration": transfer_time,
        },
        {
            "index": 5,
            "key": "lift",
            "name": "LIFT LEGS",
            "description": "Retract the unloaded feet while easing off the support angle.",
            "pose": (unloaded_height, unloaded_height, unload_target, unload_target),
            "duration": unload_time,
        },
        {
            "index": 6,
            "key": "partial_follow",
            "name": "PARTIAL FOLLOW",
            "description": "Move raised legs 25% toward the body.",
            "pose": (unloaded_height, unloaded_height, partial_target, partial_target),
            "duration": max(0.30, follow_time * 0.35),
        },
        {
            "index": 7,
            "key": "finish_legs",
            "name": "FINISH LEGS",
            "description": "Bring the raised legs fully underneath the body.",
            "pose": (unloaded_height, unloaded_height, 50, 50),
            "duration": max(0.36, follow_time * 0.65),
        },
        {
            "index": 8,
            "key": "replant",
            "name": "REPLANT",
            "description": "Extend the centered feet and take weight off the chassis.",
            "pose": (planted_height, planted_height, 50, 50),
            "duration": replant_time,
        },
        {
            "index": 9,
            "key": "finish_neutral",
            "name": "NEUTRAL BODY",
            "description": "Return body height to neutral and finish.",
            "pose": (50, 50, 50, 50),
            "duration": neutral_time,
        },
    ]
