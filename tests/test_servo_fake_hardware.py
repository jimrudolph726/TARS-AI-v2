"""Hardware-free integration tests for TARS servo control and movements."""

from __future__ import annotations

import importlib
import inspect
import sys
import threading
import time
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
        servoctl._finish_movement_watchdog(servoctl._active_watchdog)
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
        servoctl._emergency_stop_event = threading.Event()
        servoctl._movement_command_lock = threading.RLock()
        servoctl._pwm_io_lock = threading.RLock()
        servoctl._hardware_handoff_event = threading.Event()
        servoctl._hardware_lifecycle_lock = threading.RLock()
        servoctl._movement_thread_state = threading.local()
        servoctl._emergency_state_lock = threading.Lock()
        servoctl._watchdog_state_lock = threading.Lock()
        servoctl.MOVEMENT_LOCK_TIMEOUT = 0.05
        servoctl.MOVEMENT_MIN_IDLE_SECONDS = 0.0
        servoctl.SERVO_WRITE_LOCK_TIMEOUT = 0.05
        servoctl.MOVEMENT_WATCHDOG_ENABLED = True
        servoctl.MOVEMENT_WATCHDOG_TIMEOUT = 45.0
        servoctl.MOVEMENT_STALL_TIMEOUT = 8.0
        servoctl.WATCHDOG_CHECK_INTERVAL = 0.005
        servoctl._movement_last_name = None
        servoctl._movement_last_error = None
        servoctl._movement_last_success_at = None
        servoctl._movement_last_failure_at = None
        servoctl._movement_finished_at = 0.0
        servoctl._movement_consecutive_failures = 0
        servoctl._controlled_stop_reason = None
        servoctl._emergency_stop_reason = None
        servoctl._emergency_stop_at = None
        servoctl._active_watchdog = None
        servoctl._watchdog_trip_count = 0
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

    def test_low_level_gateway_rejects_invalid_or_out_of_envelope_writes(self):
        self._initialize()
        successful_before = len(self.backend.successful_writes)
        channel_zero_min, channel_zero_max = servoctl.get_servo_channel_bounds(0)

        self.assertFalse(servoctl.set_servo_pwm(10, 300))
        self.assertFalse(servoctl.set_servo_pwm(0, servoctl.SERVO_MAX_PULSE + 1))
        self.assertFalse(servoctl.set_servo_pwm(0, channel_zero_max + 1))
        self.assertFalse(servoctl.set_servo_pwm(0, channel_zero_min - 1))
        self.assertFalse(servoctl.set_servo_pwm(0, 350.5))
        self.assertFalse(servoctl.set_servo_pwm(0, float("nan")))

        self.assertEqual(len(self.backend.successful_writes), successful_before)
        self.assertTrue(any("calibrated range" in message for message in MESSAGES))

    def test_low_level_gateway_accepts_each_calibrated_boundary(self):
        self._initialize()

        for channel in range(10):
            minimum, maximum = servoctl.get_servo_channel_bounds(channel)
            with self.subTest(channel=channel, boundary="minimum"):
                self.assertTrue(servoctl.set_servo_pwm(channel, minimum))
            with self.subTest(channel=channel, boundary="maximum"):
                self.assertTrue(servoctl.set_servo_pwm(channel, maximum))

    def test_stale_saved_position_can_only_move_back_into_calibrated_range(self):
        self._initialize()
        channel = 8
        minimum, maximum = servoctl.get_servo_channel_bounds(channel)
        stale_position = maximum + 20
        servoctl.servo_positions[channel] = stale_position

        # Moving farther outside remains forbidden.
        self.assertFalse(servoctl.set_servo_pwm(channel, stale_position + 1))
        self.raw_pwm_writes.clear()

        # The interpolator may walk a stale saved position monotonically back
        # into the envelope instead of failing and stranding the joint there.
        servoctl.move_servos_timed([(channel, minimum)], duration=0.04)
        self.assertEqual(servoctl.servo_positions[channel], minimum)
        self.assertTrue(
            all(
                pulse <= stale_position
                for written_channel, pulse in self.raw_pwm_writes
                if written_channel == channel
            )
        )

    def test_calibration_gateway_can_preview_unsaved_but_absolute_safe_offset(self):
        self._initialize()
        _, current_maximum = servoctl.get_servo_channel_bounds(0)
        prospective_target = current_maximum + 5

        self.assertFalse(servoctl.set_servo_pwm(0, prospective_target))
        self.assertTrue(
            servoctl.set_calibration_servo_pwm(0, prospective_target)
        )
        self.assertFalse(
            servoctl.set_calibration_servo_pwm(0, servoctl.SERVO_MAX_PULSE + 1)
        )
        self.assertFalse(servoctl.set_calibration_servo_pwm(10, 300))

    def test_direct_low_level_write_cannot_bypass_movement_owner(self):
        self._initialize()
        successful_before = len(self.backend.successful_writes)
        result = []
        servoctl._movement_command_lock.acquire()
        try:
            worker = threading.Thread(
                target=lambda: result.append(servoctl.set_servo_pwm(0, 350)),
                daemon=True,
            )
            worker.start()
            worker.join(timeout=0.25)
        finally:
            servoctl._movement_command_lock.release()

        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
        self.assertEqual(len(self.backend.successful_writes), successful_before)

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

    def test_failed_write_releases_all_outputs_before_discarding_controller(self):
        failed_controller = self._initialize()
        for channel in (7, 8, 9):
            self.assertTrue(servoctl.set_servo_pwm(channel, servoctl.servo_positions[channel]))

        # Three failures exhaust the target write retries. The fourth simulates
        # the old failure mode where the first release attempt also failed and
        # caused the remaining channels to be skipped.
        self.backend.write_failures[8] = servoctl.MAX_RETRIES + 1
        self.assertFalse(
            servoctl.set_servo_pwm(8, servoctl.servo_positions[8] + 1)
        )

        self.assertIsNone(servoctl.pca)
        self.assertTrue(self.backend.all_outputs_disabled(failed_controller))
        self.assertFalse(any("CRITICAL:" in message for message in MESSAGES))

    def test_disable_retries_failed_channel_and_continues_with_later_channels(self):
        controller = self._initialize()
        for channel in (7, 8, 9):
            self.assertTrue(servoctl.set_servo_pwm(channel, servoctl.servo_positions[channel]))

        self.backend.write_failures[8] = 1
        self.assertTrue(servoctl.disable_all_servos())

        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assertEqual(servoctl._channels_initialized, set())

    def test_named_movement_wrapper_releases_an_energized_output(self):
        controller = self._initialize()

        def incomplete_pose():
            self.assertTrue(
                servoctl.set_servo_pwm(7, servoctl.servo_positions[7])
            )

        incomplete_pose.__module__ = "modules.module_movements"
        wrapped = servoctl.movement_command(incomplete_pose)

        self.assertTrue(wrapped())
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assertEqual(servoctl._channels_initialized, set())

    def test_failed_movement_recovers_controller_for_next_command(self):
        failed_controller = self._initialize()
        self.backend.write_failures[0] = servoctl.MAX_RETRIES

        first_result = servoctl.execute_direct_servo_command(
            "simulated_webui_failure",
            lambda: servoctl.move_servos_timed([(0, 360)], duration=0.02),
        )

        self.assertFalse(first_result)
        self.assertIsNotNone(servoctl.pca)
        self.assertIsNot(servoctl.pca, failed_controller)
        failed_status = servoctl.get_movement_status()
        self.assertEqual(failed_status["last_movement"], "simulated_webui_failure")
        self.assertTrue(failed_status["last_error"])

        second_result = servoctl.execute_direct_servo_command(
            "next_voice_command",
            lambda: servoctl.move_servos_timed([(0, 350)], duration=0.02),
        )

        self.assertTrue(second_result)
        recovered_status = servoctl.get_movement_status()
        self.assertTrue(recovered_status["ready"])
        self.assertIsNone(recovered_status["last_error"])
        self.assertEqual(recovered_status["consecutive_failures"], 0)

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

    def test_direct_servo_session_releases_for_next_named_movement(self):
        self._initialize()

        self.assertTrue(servoctl.begin_direct_servo_session("webui_move_arms"))
        self.assertTrue(servoctl.MOVING)
        servoctl.move_arm(1, 1, 1, 1, 1, 1, speed_factor=1)
        self.assertTrue(
            servoctl.end_direct_servo_session(
                "webui_move_arms", success=True
            )
        )

        self.assertFalse(servoctl.MOVING)
        self.assertTrue(servoctl.execute_registered_movement("step_forward"))
        self.assertTrue(servoctl.get_movement_status()["ready"])

    def test_cancellation_interrupts_a_timed_movement(self):
        self._initialize()
        servoctl._movement_stop_event.cancel_after_waits = 2

        @servoctl.movement_command
        def cancellable_movement():
            servoctl.move_servos_timed([(0, 460)], duration=1.0)

        self.assertFalse(cancellable_movement())
        self.assertNotEqual(servoctl.servo_positions[0], 460)
        self.assertTrue(servoctl.movement_stop_requested())

    def test_controlled_stop_releases_pwm_without_latching_future_movement(self):
        controller = self._initialize()
        servoctl._movement_stop_event = threading.Event()
        energized = threading.Event()
        result = []

        @servoctl.movement_command
        def long_pose():
            self.assertTrue(servoctl.set_servo_pwm(7, servoctl.rightMainMax))
            energized.set()
            servoctl.wait_for_movement(5.0)

        worker = threading.Thread(target=lambda: result.append(long_pose()), daemon=True)
        worker.start()
        self.assertTrue(energized.wait(timeout=0.5))
        self.assertTrue(servoctl.request_controlled_stop("test controlled stop"))
        worker.join(timeout=0.5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
        self.assertFalse(servoctl.emergency_stop_active())
        self.assertTrue(self.backend.all_outputs_disabled(controller))

        @servoctl.movement_command
        def next_pose():
            self.assertTrue(servoctl.set_servo_pwm(7, servoctl.rightMainMin))
            servoctl.disable_all_servos()

        self.assertTrue(next_pose())

    def test_emergency_power_off_is_immediate_and_latched_until_reset(self):
        controller = self._initialize()
        self.assertTrue(servoctl.set_servo_pwm(7, servoctl.rightMainMax))

        self.assertTrue(
            servoctl.emergency_power_off("test emergency", source="fake hardware")
        )

        self.assertTrue(servoctl.emergency_stop_active())
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assertFalse(servoctl.set_servo_pwm(7, servoctl.rightMainMin))
        self.assertFalse(servoctl.execute_registered_movement("step_forward"))
        self.assertFalse(servoctl.get_movement_status()["ready"])

        self.assertTrue(servoctl.reset_emergency_stop())
        self.assertFalse(servoctl.emergency_stop_active())
        self.assertTrue(servoctl.set_servo_pwm(7, servoctl.rightMainMin))
        self.assertTrue(servoctl.disable_all_servos())

    def test_emergency_release_continues_past_persistent_channel_failure(self):
        controller = self._initialize()
        for channel in (7, 8, 9):
            self.assertTrue(
                servoctl.set_servo_pwm(channel, servoctl.servo_positions[channel])
            )
        self.backend.persistent_failure_channels.add(8)

        self.assertFalse(
            servoctl.emergency_power_off(
                "persistent fake I2C failure", source="fake hardware"
            )
        )

        self.assertEqual(controller.channels[7].duty_cycle, 0)
        self.assertNotEqual(controller.channels[8].duty_cycle, 0)
        self.assertEqual(controller.channels[9].duty_cycle, 0)
        self.assertTrue(servoctl.emergency_stop_active())
        self.assertTrue(any("CRITICAL:" in message for message in MESSAGES))

        self.backend.persistent_failure_channels.clear()
        self.assertTrue(servoctl.emergency_power_off("retry release", source="test"))
        self.assertTrue(self.backend.all_outputs_disabled(controller))

    def test_emergency_release_finishes_after_an_inflight_pwm_write(self):
        controller = self._initialize()
        write_entered = threading.Event()
        release_write = threading.Event()
        writer_result = []
        emergency_result = []

        def block_first_nonzero_write(_controller, channel, value):
            if channel == 7 and value != 0 and not write_entered.is_set():
                write_entered.set()
                release_write.wait(timeout=0.5)

        self.backend.write_hook = block_first_nonzero_write
        writer = threading.Thread(
            target=lambda: writer_result.append(
                servoctl.set_servo_pwm(7, servoctl.rightMainMax)
            ),
            daemon=True,
        )
        writer.start()
        self.assertTrue(write_entered.wait(timeout=0.5))

        emergency = threading.Thread(
            target=lambda: emergency_result.append(
                servoctl.emergency_power_off("race test", source="fake hardware")
            ),
            daemon=True,
        )
        emergency.start()
        deadline = time.monotonic() + 0.5
        while not servoctl.emergency_stop_active() and time.monotonic() < deadline:
            threading.Event().wait(0.005)
        self.assertTrue(servoctl.emergency_stop_active())
        release_write.set()
        writer.join(timeout=0.5)
        emergency.join(timeout=0.5)

        self.assertFalse(writer.is_alive())
        self.assertFalse(emergency.is_alive())
        self.assertEqual(writer_result, [True])
        self.assertEqual(emergency_result, [True])
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assertEqual(controller.channels[7].duty_cycle, 0)

    def test_watchdog_emergency_stops_a_stalled_energized_movement(self):
        controller = self._initialize()
        servoctl._movement_stop_event = threading.Event()
        servoctl.MOVEMENT_WATCHDOG_TIMEOUT = 1.0
        servoctl.MOVEMENT_STALL_TIMEOUT = 0.04
        energized = threading.Event()
        result = []

        @servoctl.movement_command
        def stalled_pose():
            self.assertTrue(servoctl.set_servo_pwm(7, servoctl.rightMainMax))
            energized.set()
            threading.Event().wait(0.15)

        worker = threading.Thread(target=lambda: result.append(stalled_pose()), daemon=True)
        worker.start()
        self.assertTrue(energized.wait(timeout=0.5))
        worker.join(timeout=0.5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
        self.assertTrue(servoctl.emergency_stop_active())
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        status = servoctl.get_movement_status()
        self.assertEqual(status["watchdog"]["trip_count"], 1)
        self.assertIn("no PWM progress", status["emergency_reason"])

    def test_watchdog_enforces_total_runtime_even_with_pwm_progress(self):
        controller = self._initialize()
        servoctl._movement_stop_event = threading.Event()
        servoctl.MOVEMENT_WATCHDOG_TIMEOUT = 0.06
        servoctl.MOVEMENT_STALL_TIMEOUT = 1.0
        result = []

        @servoctl.movement_command
        def endless_progress():
            value = servoctl.rightMainMin
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                if not servoctl.set_servo_pwm(7, value):
                    break
                value = min(servoctl.rightMainMax, value + 1)
                threading.Event().wait(0.005)

        worker = threading.Thread(
            target=lambda: result.append(endless_progress()), daemon=True
        )
        worker.start()
        worker.join(timeout=0.5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
        self.assertTrue(servoctl.emergency_stop_active())
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assertIn("exceeded", servoctl.get_movement_status()["emergency_reason"])

    def test_legacy_pose_wait_is_cancellable_and_releases_pwm(self):
        controller = self._initialize()
        servoctl._movement_stop_event = threading.Event()
        first_phase = threading.Event()
        move_calls = []
        result = []

        def record_leg_phase(*args, **kwargs):
            move_calls.append((args, kwargs))
            first_phase.set()

        with patch.object(movements, "move_legs", side_effect=record_leg_phase):
            worker = threading.Thread(
                target=lambda: result.append(movements.pose()), daemon=True
            )
            worker.start()
            self.assertTrue(first_phase.wait(timeout=0.5))
            started = time.monotonic()
            servoctl.request_movement_stop()
            worker.join(timeout=0.5)
            elapsed = time.monotonic() - started

        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
        self.assertLess(elapsed, 0.25)
        # The four return phases after the three-second pose must not execute.
        self.assertLessEqual(len(move_calls), 3)
        self.assertFalse(servoctl.MOVING)
        self.assertTrue(self.backend.all_outputs_disabled(controller))
        self.assertTrue(servoctl._movement_command_lock.acquire(blocking=False))
        servoctl._movement_command_lock.release()

    def test_movement_module_contains_no_blocking_sleep_calls(self):
        self.assertNotIn("time.sleep(", inspect.getsource(movements))

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

    def test_handshake_recovers_a_stale_saved_forearm_position(self):
        controller = self._initialize()
        servoctl.ARMS_PRESENT = True
        _, maximum = servoctl.get_servo_channel_bounds(8)
        servoctl.servo_positions[8] = maximum + 20

        self.assertTrue(movements.right_handshake())

        self.assertEqual(servoctl.servo_positions[8], servoctl.rightForarmMin)
        self.assertTrue(self.backend.all_outputs_disabled(controller))

    def test_repeated_registered_movements_remain_available(self):
        self._initialize()
        servoctl.ARMS_PRESENT = True

        for movement_name in (
            "right_poke",
            "monster",
            "step_forward",
            "right_handshake",
            "step_forward",
        ):
            with self.subTest(movement=movement_name):
                self.assertTrue(
                    servoctl.execute_registered_movement(movement_name)
                )
                status = servoctl.get_movement_status()
                self.assertTrue(status["ready"])
                self.assertFalse(status["moving"])
                self.assertIsNone(status["last_error"])

        self.assertEqual(servoctl.get_movement_status()["consecutive_failures"], 0)
        self.assert_all_raw_pulses_safe()

    def test_every_registered_movement_stays_inside_calibrated_envelopes(self):
        self._initialize()
        servoctl.ARMS_PRESENT = True

        for movement_name in servoctl.MOVEMENTS:
            with self.subTest(movement=movement_name):
                servoctl.servo_positions = self._neutral_positions()
                servoctl._channels_initialized.clear()
                servoctl._movement_stop_event.clear()
                self.assertTrue(
                    servoctl.execute_registered_movement(movement_name),
                    msg=servoctl.get_movement_status().get("last_error"),
                )

        self.assert_all_raw_pulses_safe()


if __name__ == "__main__":
    unittest.main()
