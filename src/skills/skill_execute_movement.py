"""Skill: execute_movement — Send movement commands to servo motors."""

import threading
import time

from modules.module_movement_registry import HAS_ARMS, MOVEMENTS, resolve_name


MAX_MOVEMENTS_PER_REQUEST = 4
MOVEMENT_CONFIRMATION_TIMEOUT = 5.0


def _movement_prompt_list():
    lines = []
    for key, metadata in MOVEMENTS.items():
        arm_note = " (requires arms)" if metadata["type"] == HAS_ARMS else ""
        lines.append(f'     * "{key}" - {metadata["name"]}{arm_note}')
    lines.append('     * "stop" - stop the active movement')
    return "\n".join(lines)


SKILL = {
    "name": "execute_movement",
    "required_params": ["movements"],
    "followup": True,
    "description": "Perform physical locomotion, poses, and arm gestures",
    "prompt": f"""execute_movement
   Triggers: Use ONLY when the user explicitly asks TARS to move or perform a physical gesture.
   Natural-language mappings:
     * "move/go forward" -> "step_forward"
     * "move/go backward" -> "walk_backward"
     * "turn left/right" -> "turn_left_slow" / "turn_right_slow"
     * "act like a monster" -> "monster"
     * "shake my hand" -> "right_handshake"
     * "shake my left hand" -> "left_handshake"
     * "wave at me" -> "right_wave_open"
     * "poke me" -> "right_poke"
     * "take a bow" -> "bow"
     * "laugh" -> "laugh"
     * "dance" -> "happy_dance"
   Valid movements:
{_movement_prompt_list()}
   Preserve the requested order. Use at most {MAX_MOVEMENTS_PER_REQUEST} movements per call.
   Never invent movement names or servo positions. Do not infer movement from a question or suggestion.
   Parameters: {{{{"movements": ["step_forward", "right_handshake"]}}}}
   Example: {{{{"function": "execute_movement", "parameters": {{{{"movements": ["monster"]}}}}}}}}""",
    "examples": [
        """Example - Locomotion command:
User: "Walk forward and then turn left"
Response: {{"reply": "Moving now.", "function_calls": [{{"function": "execute_movement", "parameters": {{"movements": ["step_forward", "turn_left_slow"]}}}}], "new_memories": []}}""",
        """Example - Gesture command:
User: "Shake my hand"
Response: {{"reply": "Certainly.", "function_calls": [{{"function": "execute_movement", "parameters": {{"movements": ["right_handshake"]}}}}], "new_memories": []}}""",
        """Example - Character movement:
User: "Act like a monster"
Response: {{"reply": "Activating monster mode.", "function_calls": [{{"function": "execute_movement", "parameters": {{"movements": ["monster"]}}}}], "new_memories": []}}""",
    ],
}


def _normalize_movements(movements):
    """Normalize LLM output and legacy shorthand to registered movement names."""
    if isinstance(movements, str):
        movements = [movements]
    if not isinstance(movements, (list, tuple)):
        return []

    normalized = [resolve_name(move) for move in movements if str(move or "").strip()]

    # A stop command always wins. Starting another movement in the same batch
    # would immediately clear the stop signal and defeat the user's request.
    if "stop" in normalized:
        return ["stop"]
    return normalized


def _execute_movement(movements):
    """Start a sequence only after the first real PCA9685 write is confirmed."""
    from modules.module_messageQue import queue_message

    def report_failure(message):
        queue_message(f"[ERROR] {message}")
        try:
            from modules.module_main import ui_manager

            if ui_manager:
                ui_manager.update_data("SYSTEM", message, "ERROR")
        except Exception:
            pass

    movements = _normalize_movements(movements)
    if not movements:
        report_failure("No valid movement was supplied")
        return False
    if len(movements) > MAX_MOVEMENTS_PER_REQUEST:
        report_failure(
            f"Movement request contains {len(movements)} actions; the safe limit is "
            f"{MAX_MOVEMENTS_PER_REQUEST}"
        )
        return False

    unknown = [move for move in movements if move != "stop" and move not in MOVEMENTS]
    if unknown:
        report_failure(f"Movement '{unknown[0]}' was not recognized")
        return False

    try:
        import modules.module_servoctl as servoctl
    except ImportError:
        report_failure("Servo control module is not available")
        return False

    arm_movements = [
        move
        for move in movements
        if move in MOVEMENTS and MOVEMENTS[move]["type"] == HAS_ARMS
    ]
    if arm_movements and not servoctl.ARMS_PRESENT:
        report_failure(
            f"Movement '{arm_movements[0]}' requires arms, but arms_present is disabled"
        )
        return False

    write_confirmed = threading.Event()
    first_action_finished = threading.Event()
    first_action_result = {"ok": False}

    def movement_task():
        confirmation_registered = False
        try:
            if movements != ["stop"]:
                servoctl.set_movement_confirmation_event(write_confirmed)
                confirmation_registered = True

            for index, movement_name in enumerate(movements, start=1):
                if movement_name == "stop":
                    action_function = servoctl.request_movement_stop
                else:
                    action_function = lambda movement_name=movement_name: (
                        servoctl.execute_registered_movement(movement_name)
                    )

                if not callable(action_function):
                    report_failure(
                        f"Movement '{movement_name}' is registered but has no implementation"
                    )
                    break

                queue_message(
                    f"[INFO] Executing movement {index}/{len(movements)}: "
                    f"{movement_name}"
                )
                result = action_function()
                if index == 1:
                    first_action_result["ok"] = (
                        result is not False
                        and (movement_name == "stop" or write_confirmed.is_set())
                    )
                    first_action_finished.set()
                if result is False:
                    report_failure(
                        f"Movement '{movement_name}' did not start or complete; check the "
                        "PCA9685 status and movement lock"
                    )
                    break
        except Exception as error:
            if not first_action_finished.is_set():
                first_action_result["ok"] = False
                first_action_finished.set()
            report_failure(f"Unexpected error while executing movements: {error}")
        finally:
            if confirmation_registered:
                servoctl.clear_movement_confirmation_event()
            if not first_action_finished.is_set():
                first_action_finished.set()
            queue_message(f"[DEBUG] Thread completed for movements: {movements}")

    thread = threading.Thread(
        target=movement_task,
        name="voice-movement",
        daemon=True,
    )
    thread.start()

    if movements == ["stop"]:
        return True

    deadline = time.monotonic() + MOVEMENT_CONFIRMATION_TIMEOUT
    while time.monotonic() < deadline:
        if write_confirmed.wait(timeout=0.05):
            queue_message(
                f"[INFO] Movement hardware confirmed for: {movements[0]}"
            )
            return True
        if first_action_finished.is_set():
            break

    if first_action_result["ok"] and write_confirmed.is_set():
        return True

    report_failure(
        f"Movement '{movements[0]}' did not produce a confirmed servo command"
    )
    return False


def execute(parameters, context):
    """Start a requested movement, returning a reply only when it is blocked."""
    config = context.get("config", {})
    if not config.get("CONTROLS", {}).get("voicemovement"):
        return "Movement control is disabled in the current configuration."

    movements = _normalize_movements(parameters.get("movements", []))
    if not movements:
        return "I did not receive a valid movement command."
    if not _execute_movement(movements):
        return "I could not start that movement. Check the servo status and configuration."
    return None
