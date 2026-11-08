"""Release checks for durable, validated servo calibration offsets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.module_config_store import atomic_write_text, validate_typed_config_file
from modules.module_servo_tester_model import (
    ServoCalibrationModel,
    read_servo_config,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "config.ini.template"


class CalibrationRestartPersistenceTests(unittest.TestCase):
    def test_saved_offsets_survive_a_fresh_model_and_config_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.ini"
            backup_path = Path(directory) / "config.calibration-backup.ini"
            original = TEMPLATE.read_text(encoding="utf-8")
            config_path.write_text(original, encoding="utf-8")

            model = ServoCalibrationModel(read_servo_config(config_path))
            expected = {
                "left_height": 7,
                "right_height": -6,
                "left_leg": 5,
                "right_leg": -5,
                "left_main": 4,
                "right_main": -4,
                "left_forearm": 3,
                "right_forearm": -3,
                "left_hand": 2,
                "right_hand": -2,
            }
            for servo_id, value in expected.items():
                self.assertTrue(model.offset_is_safe(servo_id, value), servo_id)
                model.servos[servo_id]["value"] = value

            updated = model.update_config_text(original)
            atomic_write_text(
                config_path,
                updated,
                validator=validate_typed_config_file,
                backup_path=backup_path,
                keep_history=False,
            )

            # A new object represents closing and reopening the servo tester or
            # starting the main TARS runtime after calibration.
            restarted = ServoCalibrationModel(read_servo_config(config_path))
            actual = {
                servo_id: restarted.servos[servo_id]["value"]
                for servo_id in expected
            }

            self.assertEqual(expected, actual)
            self.assertEqual(original, backup_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
