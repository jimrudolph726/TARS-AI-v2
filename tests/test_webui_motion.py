"""HTTP contract tests for the extracted WebUI motion blueprint."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from modules.webui import motion


class FakeServoController:
    ARMS_PRESENT = True

    def __init__(self):
        self.calls = []
        self.last_error = None
        self.emergency = False

    def resolve_name(self, name):
        return name

    def get_movement_status(self, probe=False):
        return {
            "ready": not self.emergency,
            "moving": False,
            "calibration_handoff": False,
            "emergency_stop": self.emergency,
            "last_error": self.last_error,
            "probed": probe,
        }

    def execute_registered_movement(self, name):
        self.calls.append(("movement", name))
        return True

    def execute_direct_servo_command(self, name, callback):
        self.calls.append(("direct", name))
        callback()
        return True

    def begin_direct_servo_session(self, name):
        self.calls.append(("begin", name))
        return True

    def end_direct_servo_session(self, name, success, error=None):
        self.calls.append(("end", name, success, error))

    def move_legs(self, *args):
        self.calls.append(("legs", *args))
        return True

    def move_arm(self, *args):
        self.calls.append(("arm", *args))
        return True

    def wait_for_movement(self, duration):
        self.calls.append(("wait", duration))
        return True

    def emergency_power_off(self, reason, source):
        self.calls.append(("emergency", reason, source))
        self.emergency = True
        return True

    def request_controlled_stop(self, reason):
        self.calls.append(("stop", reason))
        return True

    def reset_emergency_stop(self):
        self.calls.append(("reset_emergency",))
        self.emergency = False
        return True


class WebUIMotionTests(unittest.TestCase):
    def setUp(self):
        self.servo = FakeServoController()
        motion._previous_arm_positions.update({
            key: 1 for key in motion._previous_arm_positions
        })
        self.patch = patch.object(motion, "_servo_controller", return_value=self.servo)
        self.patch.start()
        self.app = Flask(__name__)
        self.app.register_blueprint(motion.motion_blueprint)
        self.client = self.app.test_client()

    def tearDown(self):
        self.patch.stop()

    def test_named_movement_keeps_existing_http_contract(self):
        response = self.client.post("/robot_move", json={"direction": "forward"})
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["success"])
        self.assertIn(("movement", "step_forward"), self.servo.calls)

    def test_invalid_direction_is_rejected_without_hardware_call(self):
        response = self.client.post("/robot_move", json={"direction": "up"})
        self.assertEqual(400, response.status_code)
        self.assertEqual([], self.servo.calls)

    def test_controlled_and_emergency_stop_remain_distinct(self):
        controlled = self.client.post("/stop_movement")
        self.assertEqual(202, controlled.status_code)
        self.assertFalse(controlled.get_json()["servo_status"]["emergency_stop"])

        emergency = self.client.post("/disable_servos")
        self.assertEqual(200, emergency.status_code)
        self.assertTrue(emergency.get_json()["servo_status"]["emergency_stop"])

        reset = self.client.post("/enable_servos")
        self.assertEqual(200, reset.status_code)
        self.assertFalse(reset.get_json()["servo_status"]["emergency_stop"])

    def test_arm_route_owns_and_releases_direct_session(self):
        response = self.client.post("/move_arms", json={
            "left_main": 25,
            "left_forearm": 1,
            "left_hand": 1,
            "right_main": 1,
            "right_forearm": 1,
            "right_hand": 1,
            "speed": 0.85,
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual(("begin", "webui_move_arms"), self.servo.calls[0])
        self.assertIn(("legs", 80, None, None, None, 0.9), self.servo.calls)
        self.assertIn(("arm", 25, None, None, None, None, None, 0.85), self.servo.calls)
        self.assertEqual(("end", "webui_move_arms", True, None), self.servo.calls[-1])

    def test_sequence_storage_is_atomic_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            sequence_path = Path(directory) / "custom_sequences.json"
            with patch.object(motion, "_sequences_file", sequence_path):
                response = self.client.post("/save_sequence", json={
                    "name": "test wave",
                    "type": "movement",
                    "steps": [{"movement": "wave"}],
                })
                self.assertEqual(200, response.status_code)
                stored = json.loads(sequence_path.read_text(encoding="utf-8"))
                self.assertEqual("wave", stored["test wave"]["steps"][0]["movement"])

                fetched = self.client.get("/get_saved_sequences")
                self.assertEqual(stored, fetched.get_json())


if __name__ == "__main__":
    unittest.main()
