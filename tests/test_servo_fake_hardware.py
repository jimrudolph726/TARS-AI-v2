"""Hardware-free integration tests for TARS servo control and movements."""

from __future__ import annotations

import importlib
import sys
import threading
import unittest
from unittest.mock import patch

from fake_servo_hardware import (
    FakeServoBackend,
    FakeStopEvent,
    install_import_fakes,
    make_config,
)

MESSAGES = []
TEST_CONFIG = make_config()
IMPORT_FAKES = install_import_fakes(TEST_CONFIG, MESSAGES)

# Force both sides of the circular servo/movement import to use the test
# dependencies above.
sys.modules.pop("modules.module_movements", None)
sys.modules.pop("modules.module_servoctl", None)
servoctl = importlib.import_module("modules.module_servoctl")
movements = importlib.import_module("modules.module_movements")


class ServoFakeHardwareTests(unittest.TestCase):
    def setUp(self):
        MESSAGES.clear()
        TEST_CONFIG.clear()
        TEST_CONFIG.update(make_config())
        self.backend = FakeServoBackend()
        servoctl.board = IMPORT_FAKES.board
        servoctl.busio.I2C = self.backend.create_i2c
        servoctl.PCA9685 = self.backend.create_pca
        servoctl.config = TEST_CONFIG
        servoctl.pca = None
        servoctl._i2c = None
        servoctl._channels_initialized = set()
        servoctl._movement_stop_event = FakeStopEvent()
        servoctl._movement_command_lock = threading.RLock()
        servoctl._hardware_handoff_event = threading.Event()
        servoctl._hardware_lifecycle_lock = threading.RLock()
        servoctl._movement_thread_state = threading.local()
        servoctl.MOVEMENT_LOCK_TIMEOUT = 0.05
        servoctl.MOVING = False
        servoctl.battery_module = None
        servoctl._on_movement_start = None
        servoctl._on_movement_end = None
        servoctl._is_ventilate_operation = False
        servoctl.refresh_config()
        servoctl.servo_positions = self._neutral_positions()

        self.raw_pwm_writes = []
        self.real_set_servo_pwm = servoctl.set_servo_pwm

        def record_pwm(channel, pulse):
            self.raw_pwm_writes.append((channel, pulse))
            return self.real_set_servo_pwm(channel, pulse)

        servoctl.set_servo_pwm = record_pwm
        self.sleep_patch = patch.object(servoctl.time, "sleep", return_value=None)
        self.save_patch = patch.object(
            servoctl, "_save_servo_positions", return_value=None
        )
        self.sleep_patch.start()
        self.save_patch.start()

    def tearDown(self):
        self.save_patch.stop()
        self.sleep_patch.stop()
        servoctl.set_servo_pwm = self.real_set_servo_pwm
        servoctl.pca = None
        servoctl._i2c = None

    @staticmethod
    def _neutral_positions():
        return {
            0: servoctl.leftNeutralHeight,
            1: servoctl.rightNeutralHeight,
            2: servoctl.neutralLeftLeg,
            3: servoctl.neutralRightLeg,
            4: servoctl.leftMainMin,
            5: servoctl.leftForarmMin,
            6: servoctl.leftHandMin,
            7: servoctl.rightMainMin,
            8: servoctl.rightForarmMin,
            9: servoctl.rightHandMin,
        }

    def _initialize(self):
        self.assertTrue(servoctl.initialize_pca9685(retries=1, retry_delay=0))
        return self.backend.latest_controller

    @staticmethod
    def _percent(percent, start, end):
        return round(start + (end - start) * ((percent - 1) / 99))

    def assert_all_raw_pulses_safe(self):
        for channel, pulse in self.raw_pwm_writes:
            self.assertGreaterEqual(pulse, servoctl.SERVO_MIN_PULSE, channel)
            self.assertLessEqual(pulse, servoctl.SERVO_MAX_PULSE, channel)

    def test_initialization_retries_and_closes_failed_candidate(self):
        self.backend.probe_failures = 1

        self.assertTrue(servoctl.initialize_pca9685(retries=2, retry_delay=0))

        self.assertEqual(len(self.backend.controllers), 2)
        self.assertTrue(self.backend.controllers[0].deinitialized)
        self.assertTrue(self.backend.buses[0].deinitialized)
        self.assertIs(servoctl.pca, self.backend.controllers[1])
        self.assertEqual(servoctl.pca.frequency, 50)

    def test_equal_target_reenergizes_a_disabled_channel(self):
        controller = self._initialize()
        target = servoctl.servo_positions[0]
        servoctl._channels_initialized.clear()

        servoctl.move_servos_timed([(0, target)], duration=0.02)

        self.assertIn(0, servoctl._channels_initialized)
        self.assertNotEqual(controller.channels[0].duty_cycle, 0)
        self.assertIn((0, target), self.raw_pwm_writes)

    def test_offsets_map_to_the_correct_endpoint_directions(self):
        self._initialize()

        servoctl.move_legs_timed(1, 1, 1, 1, duration=0.02)
        servoctl.move_arm(1, 1, 1, 1, 1, 1, speed_factor=1)

        expected = {
            0: 227,
            1: 451,
            2: 165,
            3: 456,
            4: 520,
            5: 525,
            6: 420,
            7: 50,
            8: 175,
            9: 300,
        }
        for channel, pulse in expected.items():
            self.assertEqual(servoctl.servo_positions[channel], pulse)
        self.assert_all_raw_pulses_safe()

    def test_unsafe_target_is_rejected_before_a_pwm_write(self):
        self._initialize()
        before = list(self.raw_pwm_writes)

        with self.assertRaisesRegex(ValueError, "Unsafe PWM target"):
            servoctl.move_servos_timed([(0, 601)], duration=0.02)

        self.assertEqual(self.raw_pwm_writes, before)

    def test_failed_write_discards_controller_then_recovers(self):
        failed_controller = self._initialize()
        failed_bus = servoctl._i2c
        self.backend.write_failures[0] = servoctl.MAX_RETRIES

        self.assertFalse(servoctl.set_servo_pwm(0, 360))
        self.assertIsNone(servoctl.pca)
        self.assertTrue(failed_controller.deinitialized)
        self.assertTrue(failed_bus.deinitialized)

        self.assertTrue(servoctl.ensure_servo_hardware())
        self.assertIsNotNone(servoctl.pca)
        self.assertIsNot(servoctl.pca, failed_controller)

    def test_initialize_servos_restores_and_finishes_torque_free(self):
        self.assertTrue(servoctl.initialize_servos(startup_attempts=1))

        self.assertTrue(self.backend.all_outputs_disabled(servoctl.pca))
        self.assertEqual(servoctl._channels_initialized, set())
        self.assertTrue(any(channel < 10 for channel, _ in self.raw_pwm_writes))
        self.assert_all_raw_pulses_safe()

    def test_calibration_handoff_reclaims_hardware_torque_free(self):
        old_controller = self._initialize()
        old_bus = servoctl._i2c

        self.assertTrue(servoctl.release_hardware_for_calibration(timeout=0.1))
        self.assertTrue(old_controller.deinitialized)
        self.assertTrue(old_bus.deinitialized)
        self.assertIsNone(servoctl.pca)
        self.assertTrue(servoctl._hardware_handoff_event.is_set())

        self.assertTrue(servoctl.reclaim_hardware_after_calibration())
        self.assertFalse(servoctl._hardware_handoff_event.is_set())
        self.assertIsNotNone(servoctl.pca)
        self.assertTrue(self.backend.all_outputs_disabled(servoctl.pca))

    def test_cleanup_disables_outputs_and_deinitializes_hardware(self):
        controller = self._initialize()
        bus = servoctl._i2c
        self.assertTrue(servoctl.set_servo_pwm(0, 350))

        self.assertTrue(servoctl.cleanup(timeout=0.1))

        self.assertTrue(controller.deinitialized)
        self.assertTrue(bus.deinitialized)
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assertIsNone(servoctl.pca)
        self.assertIsNone(servoctl._i2c)

    def test_movement_commands_cannot_overlap(self):
        self._initialize()
        entered = threading.Event()
        release = threading.Event()
        results = []

        @servoctl.movement_command
        def blocking_movement():
            entered.set()
            release.wait(timeout=1)

        @servoctl.movement_command
        def second_movement():
            return True

        worker = threading.Thread(
            target=lambda: results.append(blocking_movement()), daemon=True
        )
        worker.start()
        self.assertTrue(entered.wait(timeout=1))
        self.assertFalse(second_movement())
        release.set()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results, [True])

    def test_cancellation_interrupts_a_timed_movement(self):
        self._initialize()
        servoctl._movement_stop_event.cancel_after_waits = 2

        @servoctl.movement_command
        def cancellable_movement():
            servoctl.move_servos_timed([(0, 460)], duration=1.0)

        self.assertFalse(cancellable_movement())
        self.assertNotEqual(servoctl.servo_positions[0], 460)
        self.assertTrue(servoctl.movement_stop_requested())

    def test_original_arms_step_is_bounded_and_returns_to_center(self):
        controller = self._initialize()
        servoctl.ARMS_PRESENT = True

        self.assertTrue(movements.step_forward())

        self.assertEqual(
            servoctl.servo_positions[0],
            self._percent(50, servoctl.leftUpHeight, servoctl.leftDownHeight),
        )
        self.assertEqual(
            servoctl.servo_positions[1],
            self._percent(50, servoctl.rightUpHeight, servoctl.rightDownHeight),
        )
        self.assertEqual(
            servoctl.servo_positions[2],
            self._percent(50, servoctl.forwardLeftLeg, servoctl.backLeftLeg),
        )
        self.assertEqual(
            servoctl.servo_positions[3],
            self._percent(50, servoctl.forwardRightLeg, servoctl.backRightLeg),
        )
        arms_stride = self._percent(
            8, servoctl.forwardLeftLeg, servoctl.backLeftLeg
        )
        self.assertIn((2, arms_stride), self.raw_pwm_writes)
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assert_all_raw_pulses_safe()

    def test_original_no_arms_step_uses_its_own_bounded_profile(self):
        controller = self._initialize()
        servoctl.ARMS_PRESENT = False

        self.assertTrue(movements.step_forward())

        no_arms_stride = self._percent(
            23, servoctl.forwardLeftLeg, servoctl.backLeftLeg
        )
        arms_stride = self._percent(
            8, servoctl.forwardLeftLeg, servoctl.backLeftLeg
        )
        self.assertIn((2, no_arms_stride), self.raw_pwm_writes)
        self.assertNotIn((2, arms_stride), self.raw_pwm_writes)
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assert_all_raw_pulses_safe()

    def test_monster_and_handshake_park_before_releasing_pwm(self):
        controller = self._initialize()
        servoctl.ARMS_PRESENT = True

        self.assertTrue(movements.monster())
        self.assertEqual(servoctl.servo_positions[4], servoctl.leftMainMin)
        self.assertEqual(servoctl.servo_positions[5], servoctl.leftForarmMin)
        self.assertEqual(servoctl.servo_positions[6], servoctl.leftHandMin)
        self.assertEqual(servoctl.servo_positions[7], servoctl.rightMainMin)
        self.assertEqual(servoctl.servo_positions[8], servoctl.rightForarmMin)
        self.assertEqual(servoctl.servo_positions[9], servoctl.rightHandMin)
        self.assertTrue(self.backend.all_outputs_disabled(controller))

        self.assertTrue(movements.right_handshake())
        self.assertEqual(servoctl.servo_positions[7], servoctl.rightMainMin)
        self.assertEqual(servoctl.servo_positions[8], servoctl.rightForarmMin)
        self.assertEqual(servoctl.servo_positions[9], servoctl.rightHandMin)
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assert_all_raw_pulses_safe()


if __name__ == "__main__":
    unittest.main()
