"""Regression tests for final managed-runtime startup readiness."""

from __future__ import annotations

import unittest

from modules.module_runtime import startup_ready_status


class RuntimeStartupStatusTests(unittest.TestCase):
    def test_servo_recovery_status_still_marks_runtime_ready(self):
        self.assertEqual(
            ("SYSTEM READY · SERVO RECOVERY ARMED", True),
            startup_ready_status(movement_configured=True, servos_ready=False),
        )

    def test_normal_startup_marks_runtime_ready(self):
        self.assertEqual(
            ("ALL SYSTEMS OPERATIONAL", True),
            startup_ready_status(movement_configured=True, servos_ready=True),
        )

    def test_non_movement_install_does_not_report_servo_recovery(self):
        self.assertEqual(
            ("ALL SYSTEMS OPERATIONAL", True),
            startup_ready_status(movement_configured=False, servos_ready=False),
        )


if __name__ == "__main__":
    unittest.main()
