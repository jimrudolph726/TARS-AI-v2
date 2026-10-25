"""Motion and movement-builder routes for the TARS WebUI.

Servo hardware is deliberately imported inside request handlers.  Merely
importing the WebUI must not initialize I2C or claim movement ownership.
"""

from __future__ import annotations

import inspect
import json
import re
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

from modules.module_config_store import atomic_write_text
from modules.module_messageQue import queue_message
from modules.module_movement_registry import HAS_ARMS, LEGS_ONLY, MOVEMENTS


motion_blueprint = Blueprint("motion", __name__)

_previous_arm_positions = {
    "left_main": 1,
    "left_forearm": 1,
    "left_hand": 1,
    "right_main": 1,
    "right_forearm": 1,
    "right_hand": 1,
}
_arm_state_lock = threading.Lock()
_sequences_file = Path(__file__).resolve().parents[2] / "custom_sequences.json"


def _servo_controller():
    from modules import module_servoctl
    return module_servoctl


def _movement_response(name, success_message=None):
    servo = _servo_controller()
    canonical_name = servo.resolve_name(name)
    if servo.execute_registered_movement(canonical_name):
        return jsonify({
            "success": True,
            "message": success_message or f"Movement '{canonical_name}' completed",
            "servo_status": servo.get_movement_status(),
        }), 200

    status = servo.get_movement_status()
    http_status = 409 if status["moving"] or status["calibration_handoff"] else 503
    return jsonify({
        "success": False,
        "error": status.get("last_error") or "Movement did not complete",
        "servo_status": status,
    }), http_status


@motion_blueprint.get("/api/servo/status")
def servo_status_endpoint():
    return jsonify(_servo_controller().get_movement_status(probe=True)), 200


@motion_blueprint.post("/robot_move")
def robot_move():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    direction = (request.get_json() or {}).get("direction")
    movement_names = {
        "forward": "step_forward",
        "backward": "step_backward",
        "left": "turn_left",
        "right": "turn_right",
        "forward_slow": "walk_forward",
        "backward_slow": "walk_backward",
        "left_slow": "turn_left_slow",
        "right_slow": "turn_right_slow",
    }
    if direction not in movement_names:
        valid = ", ".join(movement_names)
        return jsonify({"error": f"Invalid direction. Must be one of: {valid}"}), 400
    return _movement_response(movement_names[direction], f"Robot moved {direction}")


@motion_blueprint.get("/get_movements")
def get_movements():
    try:
        movements = [{"id": "reset_positions", "name": "Reset Position", "type": "system"}]
        movements.extend({"id": key, "name": info["name"], "type": info["type"]}
                         for key, info in MOVEMENTS.items())
        return jsonify({
            "success": True,
            "movements": movements,
            "legs_only": [
                {"id": key, "name": info["name"]}
                for key, info in MOVEMENTS.items() if info["type"] == LEGS_ONLY
            ],
            "has_arms": [
                {"id": key, "name": info["name"]}
                for key, info in MOVEMENTS.items() if info["type"] == HAS_ARMS
            ],
        }), 200
    except Exception as exc:
        queue_message(f"Error getting movements: {exc}")
        return jsonify({"error": str(exc)}), 500


@motion_blueprint.post("/execute_action")
def execute_action():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    action = (request.get_json() or {}).get("action")
    if not action:
        return jsonify({"error": "No action specified."}), 400
    if action != "reset_positions" and action not in MOVEMENTS:
        return jsonify({"error": f"Unknown action: {action}"}), 400
    display_name = "Reset positions" if action == "reset_positions" else MOVEMENTS[action]["name"]
    return _movement_response(action, f"{display_name} completed")


@motion_blueprint.post("/move_legs")
def move_legs_endpoint():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    data = request.get_json() or {}
    servo = _servo_controller()
    try:
        values = {
            "left_height": int(data.get("left_height", 50)),
            "right_height": int(data.get("right_height", 50)),
            "left_leg": int(data.get("left_leg", 50)),
            "right_leg": int(data.get("right_leg", 50)),
        }
        speed = float(data.get("speed", 0.5))
        for name, value in values.items():
            if not 5 <= value <= 100:
                return jsonify({"error": f"{name} must be between 5 and 100"}), 400
        if not 0.65 <= speed <= 1.0:
            return jsonify({"error": "speed must be between 0.65 and 1"}), 400

        succeeded = servo.execute_direct_servo_command(
            "webui_move_legs",
            lambda: servo.move_legs(
                values["left_height"], values["right_height"],
                values["left_leg"], values["right_leg"], speed,
            ),
        )
        if not succeeded:
            status = servo.get_movement_status()
            return jsonify({
                "success": False,
                "error": status.get("last_error") or "Leg movement failed",
                "servo_status": status,
            }), 503
        return jsonify({
            "success": True,
            "message": "Leg positions updated",
            "values": {**values, "speed": speed},
        }), 200
    except Exception as exc:
        queue_message(f"Error moving legs: {exc}")
        return jsonify({"error": f"Failed to move legs: {exc}"}), 500


@motion_blueprint.post("/disable_servos")
def disable_servos_endpoint():
    try:
        servo = _servo_controller()
        released = servo.emergency_power_off(
            "WebUI emergency PWM power-off", source="WebUI"
        )
        status = servo.get_movement_status()
        message = (
            "Emergency PWM power-off latched" if released
            else "Emergency stop latched, but PWM release could not be confirmed"
        )
        return jsonify({
            "success": released,
            "message": message,
            "servo_status": status,
        }), 200 if released else 503
    except Exception as exc:
        queue_message(f"Error disabling servos: {exc}")
        return jsonify({"error": f"Failed to disable servos: {exc}"}), 500


@motion_blueprint.post("/stop_movement")
def stop_movement_endpoint():
    servo = _servo_controller()
    servo.request_controlled_stop("WebUI controlled stop")
    return jsonify({
        "success": True,
        "message": "Controlled stop requested",
        "servo_status": servo.get_movement_status(),
    }), 202


@motion_blueprint.post("/enable_servos")
def enable_servos_endpoint():
    try:
        servo = _servo_controller()
        reset = servo.reset_emergency_stop()
        status = servo.get_movement_status(probe=reset)
        message = (
            "Emergency latch reset; outputs remain disabled" if reset
            else "Emergency latch reset was refused"
        )
        return jsonify({
            "success": reset,
            "message": message,
            "servo_status": status,
        }), 200 if reset else 503
    except Exception as exc:
        queue_message(f"Error resetting emergency servo stop: {exc}")
        return jsonify({"error": f"Failed to reset emergency stop: {exc}"}), 500


@motion_blueprint.post("/reset_positions")
def reset_positions_endpoint():
    return _movement_response("reset_positions", "Positions reset")


@motion_blueprint.post("/neutral_legs")
def neutral_legs_endpoint():
    return _movement_response("neutral_legs", "Legs neutralized")


@motion_blueprint.post("/move_arms")
def move_arms_endpoint():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json() or {}
    servo = _servo_controller()
    session_started = False
    session_succeeded = False
    session_error = None
    try:
        positions = {
            "left_main": int(data.get("left_main", 1)),
            "left_forearm": int(data.get("left_forearm", 1)),
            "left_hand": int(data.get("left_hand", 1)),
            "right_main": int(data.get("right_main", 1)),
            "right_forearm": int(data.get("right_forearm", 1)),
            "right_hand": int(data.get("right_hand", 1)),
        }
        speed = float(data.get("speed", 0.85))
        for name, value in positions.items():
            if not 1 <= value <= 100:
                return jsonify({"error": f"{name} must be between 1 and 100"}), 400
        if not 0.65 <= speed <= 1.0:
            return jsonify({"error": "speed must be between 0.65 and 1"}), 400
        if not servo.begin_direct_servo_session("webui_move_arms"):
            status = servo.get_movement_status()
            return jsonify({
                "success": False,
                "error": status.get("last_error") or "Arm movement is unavailable",
                "servo_status": status,
            }), 503
        session_started = True

        with _arm_state_lock:
            previous = dict(_previous_arm_positions)
            left_active = any(positions[key] != 1 for key in ("left_main", "left_forearm", "left_hand"))
            right_active = any(positions[key] != 1 for key in ("right_main", "right_forearm", "right_hand"))
            if left_active:
                servo.move_legs(80, None, None, None, 0.9)
                servo.move_legs(80, None, 65, None, 0.9)
            if right_active:
                servo.move_legs(None, 80, None, None, 0.9)
                servo.move_legs(None, 80, None, 65, 0.9)

            _move_arm_side(servo, "left", positions, previous, speed)
            _move_arm_side(servo, "right", positions, previous, speed)
            _previous_arm_positions.update(positions)

            if not left_active:
                servo.move_legs(80, None, 50, None, 0.9)
                servo.move_legs(50, None, None, None, 0.9)
            if not right_active:
                servo.move_legs(None, 80, None, 50, 0.9)
                servo.move_legs(None, 50, None, None, 0.9)

        session_succeeded = True
        return jsonify({
            "success": True,
            "message": "Arm positions updated with sequential movement",
            "values": {**positions, "speed": speed},
        }), 200
    except Exception as exc:
        session_error = str(exc)
        queue_message(f"Error moving arms: {exc}")
        return jsonify({"error": f"Failed to move arms: {exc}"}), 500
    finally:
        if session_started:
            servo.end_direct_servo_session(
                "webui_move_arms",
                success=session_succeeded,
                error=session_error,
            )


def _move_arm_side(servo, side, positions, previous, speed):
    keys = [f"{side}_main", f"{side}_forearm", f"{side}_hand"]
    increasing = sum(positions[key] for key in keys) > sum(previous[key] for key in keys)
    order = keys if increasing else list(reversed(keys))
    argument_index = {
        "left_main": 0, "left_forearm": 1, "left_hand": 2,
        "right_main": 3, "right_forearm": 4, "right_hand": 5,
    }
    for key in order:
        if positions[key] == previous[key]:
            continue
        args = [None] * 6
        args[argument_index[key]] = positions[key]
        servo.move_arm(*args, speed)


def _load_sequences():
    if not _sequences_file.exists():
        return {}
    try:
        return json.loads(_sequences_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_sequences(data):
    atomic_write_text(
        _sequences_file,
        json.dumps(data, indent=2),
        validator=None,
        create_backup=True,
    )


@motion_blueprint.get("/get_arms_status")
def get_arms_status():
    return jsonify({"arms_present": bool(_servo_controller().ARMS_PRESENT)}), 200


@motion_blueprint.post("/play_sequence")
def play_sequence():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    return _execute_steps((request.get_json() or {}).get("steps", []))


@motion_blueprint.post("/save_sequence")
def save_sequence():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    sequences = _load_sequences()
    sequences[name] = {
        "type": data.get("type", "movement"),
        "quick": bool(data.get("quick", False)),
        "steps": data.get("steps", []),
    }
    _save_sequences(sequences)
    return jsonify({"success": True, "name": name}), 200


@motion_blueprint.get("/get_saved_sequences")
def get_saved_sequences():
    return jsonify(_load_sequences()), 200


@motion_blueprint.post("/delete_saved_sequence")
def delete_saved_sequence():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    name = (request.get_json() or {}).get("name", "").strip()
    sequences = _load_sequences()
    if name not in sequences:
        return jsonify({"error": f"'{name}' not found"}), 404
    del sequences[name]
    _save_sequences(sequences)
    return jsonify({"success": True}), 200


@motion_blueprint.post("/play_saved_sequence")
def play_saved_sequence():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    name = (request.get_json() or {}).get("name", "").strip()
    sequences = _load_sequences()
    if name not in sequences:
        return jsonify({"error": f"'{name}' not found"}), 404
    entry = sequences[name]
    return _execute_steps(entry.get("steps", []) if isinstance(entry, dict) else entry)


def _execute_steps(steps):
    servo = _servo_controller()
    for index, step in enumerate(steps, start=1):
        if step.get("movement"):
            if not servo.execute_registered_movement(step["movement"]):
                return _sequence_failure(servo, index)
            continue

        def execute_pose(step=step):
            speed = step.get("speed", 0.85)
            servo.move_legs(
                step.get("left_height", 50), step.get("right_height", 50),
                step.get("left_leg", 50), step.get("right_leg", 50), speed,
            )
            if servo.ARMS_PRESENT:
                arm_values = [
                    step.get("left_main"), step.get("left_forearm"), step.get("left_hand"),
                    step.get("right_main"), step.get("right_forearm"), step.get("right_hand"),
                ]
                if any(value is not None for value in arm_values):
                    servo.move_arm(*arm_values, speed)
            hold = float(step.get("hold_time", 0.0) or 0.0)
            if hold > 0:
                servo.wait_for_movement(hold)

        if not servo.execute_direct_servo_command(
            f"webui_sequence_step_{index}", execute_pose
        ):
            return _sequence_failure(servo, index)

    if not servo.execute_registered_movement("reset_positions"):
        return _sequence_failure(servo, None, "Sequence reset failed")
    return jsonify({"success": True, "servo_status": servo.get_movement_status()}), 200


def _sequence_failure(servo, index=None, fallback=None):
    status = servo.get_movement_status()
    response = {
        "success": False,
        "error": status.get("last_error") or fallback or f"Step {index} failed",
        "servo_status": status,
    }
    if index is not None:
        response["failed_step"] = index
    return jsonify(response), 503


@motion_blueprint.get("/get_movement_steps/<name>")
def get_movement_steps(name):
    from modules import module_movements
    try:
        source = inspect.getsource(getattr(module_movements, name))
    except (AttributeError, OSError):
        return jsonify({"error": f"Movement '{name}' not found"}), 404
    steps = _parse_movement_steps(source)
    if not steps:
        return jsonify({"error": f"No move_legs calls found in '{name}'"}), 422
    return jsonify({"name": name, "steps": steps}), 200


def _parse_movement_steps(source):
    def parse_value(value, default=50):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return default

    def extract(lines):
        result = []
        index = 0
        while index < len(lines):
            line = lines[index]
            loop = re.search(r"for\s+\w+\s+in\s+range\((\d+)\)\s*:", line)
            if loop:
                repeat = int(loop.group(1))
                indent = len(line) - len(line.lstrip())
                body = []
                index += 1
                while index < len(lines):
                    candidate = lines[index]
                    if not candidate.strip():
                        index += 1
                        continue
                    if len(candidate) - len(candidate.lstrip()) <= indent:
                        break
                    body.append(candidate)
                    index += 1
                nested = extract(body)
                for _ in range(repeat):
                    result.extend(dict(step) for step in nested)
                continue

            leg_call = re.search(r"move_legs\(([^)]+)\)", line)
            if leg_call:
                args = [value.strip() for value in leg_call.group(1).split(",")]
                if len(args) >= 4:
                    speed = 0.85
                    if len(args) > 4 and re.fullmatch(r"[\d.]+", args[4]):
                        speed = round(float(args[4]), 2)
                    step = {
                        "movement": None,
                        "left_height": parse_value(args[0]),
                        "right_height": parse_value(args[1]),
                        "left_leg": parse_value(args[2]),
                        "right_leg": parse_value(args[3]),
                        "left_main": None, "left_forearm": None, "left_hand": None,
                        "right_main": None, "right_forearm": None, "right_hand": None,
                        "speed": speed,
                        "hold_time": 0.0,
                    }
                    for following in lines[index + 1:index + 3]:
                        sleep = re.search(r"time\.sleep\(([^)]+)\)", following)
                        if sleep:
                            try:
                                step["hold_time"] = float(sleep.group(1))
                            except ValueError:
                                pass
                            break
                    result.append(step)

            arm_call = re.search(r"move_arm\(([^)]+)\)", line)
            if arm_call and result:
                args = [value.strip() for value in arm_call.group(1).split(",")]
                if len(args) >= 6:
                    keys = [
                        "left_main", "left_forearm", "left_hand",
                        "right_main", "right_forearm", "right_hand",
                    ]
                    for key, value in zip(keys, args[:6]):
                        try:
                            result[-1][key] = int(round(float(value)))
                        except (TypeError, ValueError):
                            result[-1][key] = None
            index += 1
        return result

    return extract(source.splitlines())
