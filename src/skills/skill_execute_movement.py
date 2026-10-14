"""Skill: execute_movement — Send movement commands to servo motors."""

import threading

SKILL = {
    "name": "execute_movement",
    "required_params": ["movements"],
    "followup": True,
    "description": "Perform physical movements and gestures",
    "prompt": """execute_movement
   Triggers: Use ONLY when user explicitly commands movement
     * "walk forward", "turn left", "step back", "move backward"
     * "go forward", "turn right"
   Valid movements:
     * "forward" - walk forward
     * "backward" - walk backward
     * "left" - turn left slowly
     * "right" - turn right slowly
     * "stop" - stop the active movement
   Do NOT infer or guess movement from suggestions or questions
   Parameters: {{"movements": ["forward", "backward", "left", "right"]}}
   Example: {{"function": "execute_movement", "parameters": {{"movements": ["forward", "forward", "left"]}}}}""",
    "examples": [
        """Example - Movement command:
User: "Walk forward and then turn left"
Response: {{"reply": "Moving now.", "function_calls": [{{"function": "execute_movement", "parameters": {{"movements": ["forward", "left"]}}}}], "new_memories": []}}""",
    ],
}


def _execute_movement(movements):
    """Execute a sequence of movements in a separate thread."""
    from modules.module_messageQue import queue_message

    def report_failure(message):
        queue_message(f"[ERROR] {message}")
        try:
            from modules.module_main import ui_manager

            if ui_manager:
                ui_manager.update_data("SYSTEM", message, "ERROR")
        except Exception:
            pass

    # Lazy import servo functions
    try:
        from modules.module_servoctl import (
            ensure_servo_hardware,
            request_movement_stop,
            step_forward,
            walk_backward,
            turn_right_slow,
            turn_left_slow,
        )
    except ImportError:
        report_failure("Servo control module is not available")
        return False

    requires_hardware = any(str(move).lower() != "stop" for move in movements)
    if requires_hardware and not ensure_servo_hardware():
        report_failure(
            "PCA9685 servo controller is unavailable; movement was not started"
        )
        return False

    action_map = {
        # The original single-step gait is the physically validated forward
        # movement. Repeated forward requests can safely build longer travel.
        "forward": step_forward,
        "backward": walk_backward,
        "left": turn_left_slow,
        "right": turn_right_slow,
        "stop": request_movement_stop,
    }

    def movement_task():
        try:
            for i, move in enumerate(movements, start=1):
                action_function = action_map.get(move)
                if callable(action_function):
                    queue_message(f"[INFO] Executing movement {i}/{len(movements)}: {move}")
                    result = action_function()
                    if result is False:
                        report_failure(
                            f"Movement '{move}' did not start or complete; check the "
                            "PCA9685 status and movement lock"
                        )
                        break
                else:
                    report_failure(f"Movement '{move}' was not recognized")
        except Exception as e:
            report_failure(f"Unexpected error while executing movements: {e}")
        finally:
            queue_message(f"[DEBUG] Thread completed for movements: {movements}")

    thread = threading.Thread(target=movement_task, daemon=True)
    thread.start()
    return True


def execute(parameters, context):
    """Start movement, returning an explanatory reply only when it is blocked."""
    config = context.get("config", {})
    if not config.get("CONTROLS", {}).get("voicemovement"):
        return "Movement control is disabled in the current configuration."

    movements = parameters.get("movements", [])
    if movements:
        if not _execute_movement(movements):
            return "I couldn't access the servo controller, so I did not move."
    return None
