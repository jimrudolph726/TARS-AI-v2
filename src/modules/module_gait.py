"""Pure gait profiles shared by movement code and diagnostic interfaces."""

from __future__ import annotations


_ORIGINAL_FORWARD_STEP_PHASES = {
    True: (
        ("BODY SWING", "Original raised forward swing.", (32, 32, 25, 25), 0.9),
        ("SUPPORT TRANSFER", "Original chassis support-transfer pose.", (88, 88, 8, 8), 1.0),
        ("LEG RECOVERY", "Original leg recovery after the body advances.", (15, 15, 17, 17), 0.9),
        ("LEG PLANT", "Original intermediate leg plant.", (75, 75, 24, 24), 0.9),
        ("LEGS FOLLOW", "Original legs-under-body recovery.", (70, 70, 50, 50), 0.9),
        ("FINAL NEUTRAL", "Original balanced finishing pose.", (50, 50, 50, 50), 0.9),
    ),
    False: (
        ("BODY SWING", "Original raised forward swing.", (42, 42, 40, 40), 0.9),
        ("SUPPORT TRANSFER", "Original chassis support-transfer pose.", (70, 70, 23, 23), 0.9),
        ("LEG RECOVERY", "Original leg recovery after the body advances.", (30, 30, 30, 30), 0.8),
        ("LEG PLANT", "Original intermediate leg plant.", (70, 70, 35, 35), 0.9),
        ("LEGS FOLLOW", "Original legs-under-body recovery.", (60, 60, 50, 50), 0.9),
        ("FINAL NEUTRAL", "Original balanced finishing pose.", (50, 50, 50, 50), 0.9),
    ),
}


def _mirror_leg_rotation(pose: tuple[int, int, int, int]):
    """Mirror only forward/back leg rotation around calibrated neutral."""
    left_height, right_height, left_leg, right_leg = pose
    return left_height, right_height, 100 - left_leg, 100 - right_leg


def original_step_phases(direction: str, arms_present: bool) -> list[dict]:
    """Return the field-proven fast step or its exact backward mirror.

    Height, phase order, and speed remain identical in both directions. Only
    the normalized forward/back leg percentages are mirrored around 50. Raw
    PWM values must not be inverted because calibration already accounts for
    each physical servo's endpoint direction.
    """
    if direction not in ("forward", "backward"):
        raise ValueError(f"Unsupported original step direction: {direction}")

    raw_phases = _ORIGINAL_FORWARD_STEP_PHASES[bool(arms_present)]
    phases = []
    for index, (name, description, forward_pose, speed) in enumerate(
        raw_phases, start=1
    ):
        pose = (
            forward_pose
            if direction == "forward"
            else _mirror_leg_rotation(forward_pose)
        )
        if direction == "backward":
            description = description.replace("forward", "backward").replace(
                "advances", "retreats"
            )
        phases.append({
            "index": index,
            "key": f"original_{direction}_{index}",
            "name": name,
            "description": description,
            "pose": pose,
            "speed": speed,
        })
    return phases


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
        diagnostic_contact_height = 88
        support_forward, unload_forward = 8, 17
    else:
        stride = 26
        raised_height, planted_height, unloaded_height = 38, 72, 22
        diagnostic_contact_height = planted_height
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
        "diagnostic_contact_height": diagnostic_contact_height,
        "unloaded_height": unloaded_height,
        "timings": timings,
    }


def body_swing_diagnostic_phases(direction: str, arms_present: bool) -> list[dict]:
    """Return the exact original/mirrored step poses for prefix diagnostics.

    Each pose includes the original ``move_legs`` speed factor. The diagnostic
    runner replays neutral through the selected pose without pausing between
    transitions, then holds that pose for inspection.
    """
    return original_step_phases(direction, arms_present)
