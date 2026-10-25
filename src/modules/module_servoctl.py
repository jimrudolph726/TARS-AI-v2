"""
Module: Servo Controller V3.1
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""

from __future__ import division
import time
import os
import math
import threading
from functools import wraps
from numbers import Integral, Real
import board
import busio
from adafruit_pca9685 import PCA9685

from modules.module_messageQue import queue_message
from modules.module_config import load_config

config = load_config()

NEUTRAL_LEFT_HEIGHT = 350
NEUTRAL_RIGHT_HEIGHT = 350
NEUTRAL_LEFT_LEG = 300
NEUTRAL_RIGHT_LEG = 300

global_arm_speed = 0.5
global_easing_strength = 0.6

SERVO_UPDATE_HZ = 50.0
SERVO_MIN_PULSE = 10
SERVO_MAX_PULSE = 600

_movement_stop_event = threading.Event()
_emergency_stop_event = threading.Event()
_movement_command_lock = threading.RLock()
_pwm_io_lock = threading.RLock()
_hardware_handoff_event = threading.Event()
_hardware_lifecycle_lock = threading.RLock()
_movement_thread_state = threading.local()
_emergency_state_lock = threading.Lock()
_watchdog_state_lock = threading.Lock()

MOVEMENT_LOCK_TIMEOUT = 8.0
MOVEMENT_MIN_IDLE_SECONDS = 0.75
SERVO_WRITE_LOCK_TIMEOUT = 0.25
PCA_PROBE_CHANNEL = 15
MOVEMENT_WATCHDOG_ENABLED = bool(
    config.get("SERVO", {}).get("movement_watchdog_enabled", True)
)
MOVEMENT_WATCHDOG_TIMEOUT = float(
    config.get("SERVO", {}).get("movement_watchdog_timeout", 45.0)
)
MOVEMENT_STALL_TIMEOUT = float(
    config.get("SERVO", {}).get("movement_stall_timeout", 8.0)
)
WATCHDOG_CHECK_INTERVAL = 0.1

_movement_status_lock = threading.Lock()
_movement_last_name = None
_movement_last_error = None
_movement_last_success_at = None
_movement_last_failure_at = None
_movement_finished_at = 0.0
_movement_consecutive_failures = 0
_controlled_stop_reason = None
_emergency_stop_reason = None
_emergency_stop_at = None
_active_watchdog = None
_watchdog_trip_count = 0


class MovementCancelled(RuntimeError):
    """Raised internally when an active movement is asked to stop."""


def request_controlled_stop(reason="Controlled stop requested"):
    """Ask the active routine to stop at its next cooperative checkpoint.

    This does not latch movement offline. The movement owner remains
    responsible for leaving its critical section, and its wrapper releases PWM
    before another command may start.
    """
    global _controlled_stop_reason

    _controlled_stop_reason = str(reason or "Controlled stop requested")
    was_set = _movement_stop_event.is_set()
    _movement_stop_event.set()
    if not was_set and not _emergency_stop_event.is_set():
        queue_message(f"MOVEMENT: {_controlled_stop_reason}")
    return True


def request_movement_stop(reason="Controlled stop requested"):
    """Backward-compatible name for a controlled, non-latching stop."""
    return request_controlled_stop(reason)


def movement_stop_requested():
    return _movement_stop_event.is_set()


def emergency_stop_active():
    """Return whether emergency PWM-off is latched."""
    return _emergency_stop_event.is_set()


def emergency_power_off(reason="Emergency power-off requested", source="manual"):
    """Immediately request cancellation, cut PWM, and latch movement offline.

    This deliberately does not wait for the movement lock. In an emergency the
    release attempt must not sit behind a stalled movement thread. The physical
    rear power switch remains the final authority if I2C itself is unavailable.
    """
    global _channels_initialized, _emergency_stop_reason, _emergency_stop_at

    reason = str(reason or "Emergency power-off requested")
    with _emergency_state_lock:
        first_trip = not _emergency_stop_event.is_set()
        _emergency_stop_reason = reason
        _emergency_stop_at = time.time()
        _emergency_stop_event.set()
        _movement_stop_event.set()

    controller = pca
    failed_channels = _disable_controller_outputs(controller)
    _channels_initialized.intersection_update(failed_channels)
    if first_trip:
        queue_message(
            f"EMERGENCY: Servo PWM power-off latched by {source}: {reason}"
        )
    if failed_channels:
        queue_message(
            "CRITICAL: Emergency PWM release could not be confirmed on "
            f"channel(s) {', '.join(map(str, failed_channels))}; "
            "use the physical servo-power switch"
        )
    return not failed_channels


def reset_emergency_stop():
    """Clear the emergency latch without energizing or moving a servo."""
    global _emergency_stop_reason, _emergency_stop_at, _controlled_stop_reason

    if MOVING:
        queue_message("ERROR: Emergency stop cannot be reset while movement is active")
        return False
    if pca is not None:
        if not _probe_controller(pca):
            queue_message("ERROR: Emergency stop reset refused; PCA9685 health check failed")
            return False
        if not disable_all_servos():
            queue_message("ERROR: Emergency stop reset refused; PWM release is unconfirmed")
            return False

    with _emergency_state_lock:
        _emergency_stop_event.clear()
        _movement_stop_event.clear()
        _emergency_stop_reason = None
        _emergency_stop_at = None
        _controlled_stop_reason = None
    queue_message("SERVO: Emergency power-off latch reset; outputs remain disabled")
    return True


def _mark_movement_progress():
    with _watchdog_state_lock:
        if _active_watchdog is not None:
            _active_watchdog["last_progress"] = time.monotonic()
            _active_watchdog["writes"] += 1


def _movement_watchdog_worker(state):
    global _watchdog_trip_count

    while not state["done"].wait(WATCHDOG_CHECK_INTERVAL):
        with _watchdog_state_lock:
            if _active_watchdog is not state:
                return
            started_at = state["started_at"]
            last_progress = state["last_progress"]
            writes = state["writes"]

        now = time.monotonic()
        reason = None
        if MOVEMENT_WATCHDOG_TIMEOUT > 0 and now - started_at > MOVEMENT_WATCHDOG_TIMEOUT:
            reason = (
                f"movement '{state['name']}' exceeded "
                f"{MOVEMENT_WATCHDOG_TIMEOUT:g}s"
            )
        elif (
            MOVEMENT_STALL_TIMEOUT > 0
            and writes > 0
            and bool(_channels_initialized)
            and now - last_progress > MOVEMENT_STALL_TIMEOUT
        ):
            reason = (
                f"movement '{state['name']}' made no PWM progress for "
                f"{MOVEMENT_STALL_TIMEOUT:g}s"
            )

        if reason is None:
            continue

        with _watchdog_state_lock:
            if _active_watchdog is not state or state["done"].is_set():
                return
            state["tripped"] = True
            state["reason"] = reason
            _watchdog_trip_count += 1
        emergency_power_off(reason, source="movement watchdog")
        return


def _start_movement_watchdog(name):
    global _active_watchdog

    if not MOVEMENT_WATCHDOG_ENABLED:
        return None
    now = time.monotonic()
    state = {
        "name": str(name),
        "started_at": now,
        "last_progress": now,
        "writes": 0,
        "tripped": False,
        "reason": None,
        "done": threading.Event(),
    }
    with _watchdog_state_lock:
        _active_watchdog = state
    threading.Thread(
        target=_movement_watchdog_worker,
        args=(state,),
        name=f"servo-watchdog-{name}",
        daemon=True,
    ).start()
    return state


def _finish_movement_watchdog(state):
    global _active_watchdog

    if state is None:
        return
    state["done"].set()
    with _watchdog_state_lock:
        if _active_watchdog is state:
            _active_watchdog = None


def set_movement_confirmation_event(event):
    """Register a per-thread event set after the first successful PWM write."""
    _movement_thread_state.confirmation_event = event


def clear_movement_confirmation_event():
    """Remove a movement confirmation event from the current worker thread."""
    if hasattr(_movement_thread_state, "confirmation_event"):
        del _movement_thread_state.confirmation_event


def _confirm_servo_write():
    _mark_movement_progress()
    event = getattr(_movement_thread_state, "confirmation_event", None)
    if event is not None:
        event.set()


def movement_command(function):
    """Serialize public movement commands and make them cancellable.

    Existing movement functions already own the MOVING flag and lifecycle
    callbacks.  This wrapper adds the missing cross-thread lock without
    changing their public API.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        global _movement_finished_at, _controlled_stop_reason

        watchdog_state = None

        if _emergency_stop_event.is_set():
            message = _emergency_stop_reason or "Emergency power-off is latched"
            _record_movement_failure(function.__name__, message)
            queue_message(
                f"ERROR: MOVEMENT: Emergency power-off is latched; "
                f"ignored {function.__name__}"
            )
            return False
        if _hardware_handoff_event.is_set():
            message = "Hardware is reserved for servo calibration"
            _record_movement_failure(function.__name__, message)
            queue_message(f"MOVEMENT: {message}; ignored {function.__name__}")
            return False
        if not _movement_command_lock.acquire(timeout=MOVEMENT_LOCK_TIMEOUT):
            message = f"Timed out waiting to run {function.__name__}"
            _record_movement_failure(function.__name__, message)
            queue_message(f"ERROR: MOVEMENT: {message}")
            return False
        _movement_stop_event.clear()
        _controlled_stop_reason = None
        try:
            if MOVING:
                message = "Another movement is still active"
                _record_movement_failure(function.__name__, message)
                queue_message(f"ERROR: MOVEMENT: {message}; could not run {function.__name__}")
                return False
            if not ensure_servo_hardware():
                message = "Servo controller unavailable"
                _record_movement_failure(function.__name__, message)
                queue_message(f"ERROR: MOVEMENT: {message}; ignored {function.__name__}")
                return False

            # Rapidly launching large gestures can repeatedly hit the servo
            # supply with peak current. Give the rail a short recovery window
            # between complete commands while keeping individual gait timing
            # unchanged.
            idle_remaining = (
                MOVEMENT_MIN_IDLE_SECONDS
                - (time.monotonic() - _movement_finished_at)
            )
            if idle_remaining > 0 and _movement_stop_event.wait(idle_remaining):
                raise MovementCancelled()

            watchdog_state = _start_movement_watchdog(function.__name__)
            result = function(*args, **kwargs)
            if result is False:
                _record_movement_failure(
                    function.__name__, "Movement implementation returned failure"
                )
                return False
            # Named pose scripts are required to finish torque-free. Most
            # release PWM in their own finally block; this catches either an
            # omitted release or a channel that remained active after bounded
            # I2C retries. Direct WebUI positioning is intentionally excluded
            # because those controls may hold a requested manual pose.
            if (
                function.__module__ == "modules.module_movements"
                and _channels_initialized
                and not disable_all_servos()
            ):
                raise RuntimeError(
                    "Unable to confirm that all servo PWM outputs were released"
                )
            if _movement_stop_event.is_set():
                detail = (
                    _emergency_stop_reason
                    if _emergency_stop_event.is_set()
                    else (_controlled_stop_reason or "Movement was stopped")
                )
                _record_movement_failure(function.__name__, detail)
                return False
            _record_movement_success(function.__name__)
            return True
        except MovementCancelled:
            disable_all_servos()
            if _emergency_stop_event.is_set():
                detail = _emergency_stop_reason or "Emergency power-off"
                queue_message(
                    f"EMERGENCY: Aborted {function.__name__}: {detail}"
                )
            else:
                detail = _controlled_stop_reason or "Movement was stopped"
                queue_message(f"MOVEMENT: Controlled stop completed for {function.__name__}")
            _record_movement_failure(function.__name__, detail)
            return False
        except Exception as exc:
            detail = (
                _emergency_stop_reason
                if _emergency_stop_event.is_set()
                else _describe_hardware_error(exc)
            )
            # Exceptions can occur after one or more channels were energized.
            # Release every output before attempting controller recovery.
            disable_all_servos()
            _record_movement_failure(function.__name__, detail)
            queue_message(
                f"ERROR: MOVEMENT: {function.__name__} failed: {detail}"
            )

            # A failed PWM write discards the cached controller. Reopen it now
            # so the next WebUI or voice command does not inherit an offline
            # controller. Never repeat the movement automatically: it may have
            # completed only part of its physical path.
            if (
                pca is None
                and not _hardware_handoff_event.is_set()
                and not _emergency_stop_event.is_set()
            ):
                if initialize_pca9685(retries=1):
                    queue_message(
                        "SERVO: Controller recovered after movement failure; "
                        "the next command may proceed"
                    )
            return False
        finally:
            _finish_movement_watchdog(watchdog_state)
            _movement_finished_at = time.monotonic()
            _movement_command_lock.release()
    return wrapped


def _record_movement_success(name):
    global _movement_last_name, _movement_last_error
    global _movement_last_success_at, _movement_consecutive_failures

    with _movement_status_lock:
        _movement_last_name = str(name)
        _movement_last_error = None
        _movement_last_success_at = time.time()
        _movement_consecutive_failures = 0


def _record_movement_failure(name, message):
    global _movement_last_name, _movement_last_error
    global _movement_last_failure_at, _movement_consecutive_failures

    with _movement_status_lock:
        _movement_last_name = str(name)
        _movement_last_error = str(message)
        _movement_last_failure_at = time.time()
        _movement_consecutive_failures += 1


def get_movement_status(probe=False):
    """Return a thread-safe snapshot suitable for UI and diagnostics."""
    controller_connected = pca is not None
    if probe and controller_connected and not _hardware_handoff_event.is_set():
        controller_connected = _probe_controller(pca)

    with _watchdog_state_lock:
        watchdog = _active_watchdog
        watchdog_status = {
            "active": watchdog is not None,
            "movement": watchdog["name"] if watchdog else None,
            "elapsed": (
                round(time.monotonic() - watchdog["started_at"], 3)
                if watchdog else None
            ),
            "progress_age": (
                round(time.monotonic() - watchdog["last_progress"], 3)
                if watchdog else None
            ),
            "writes": watchdog["writes"] if watchdog else 0,
            "tripped": bool(watchdog and watchdog["tripped"]),
            "trip_count": _watchdog_trip_count,
        }

    with _movement_status_lock:
        return {
            "ready": bool(
                controller_connected
                and not MOVING
                and not _hardware_handoff_event.is_set()
                and not _emergency_stop_event.is_set()
            ),
            "moving": bool(MOVING),
            "controller_connected": bool(controller_connected),
            "calibration_handoff": _hardware_handoff_event.is_set(),
            "emergency_stop": _emergency_stop_event.is_set(),
            "emergency_reason": _emergency_stop_reason,
            "emergency_at": _emergency_stop_at,
            "watchdog": watchdog_status,
            "energized_channels": sorted(_channels_initialized),
            "last_movement": _movement_last_name,
            "last_error": _movement_last_error,
            "last_success_at": _movement_last_success_at,
            "last_failure_at": _movement_last_failure_at,
            "consecutive_failures": _movement_consecutive_failures,
        }


def wait_for_movement(seconds):
    """Cancellable replacement for sleeps inside newly defined gaits."""
    if seconds > 0 and _movement_stop_event.wait(seconds):
        raise MovementCancelled()

SERVO_POSITIONS_FILE = os.path.expanduser("~/.servo_positions.json")

def _load_servo_positions():
    
    import json
    try:
        with open(SERVO_POSITIONS_FILE, 'r') as f:
            positions = json.load(f)
            return {int(k): v for k, v in positions.items()}
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"[SERVO] No saved positions found, starting fresh")
        return {}

def _save_servo_positions():
    
    import json
    try:
        with open(SERVO_POSITIONS_FILE, 'w') as f:
            json.dump(servo_positions, f)
    except Exception as e:
        print(f"[SERVO] Warning: Could not save positions: {e}")

servo_positions = _load_servo_positions()

# Saved positions describe where each servo was last commanded, not whether
# the PCA9685 output is currently energized. Every process starts with unknown
# hardware-output state and must issue at least one PWM write per active channel.
_channels_initialized = set()

pca = None
_i2c = None
MAX_RETRIES = 3

battery_module = None


def _describe_hardware_error(exc):
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 121:
        return "I2C remote I/O error; check PCA9685 power, ground, SDA, and SCL wiring"
    return str(exc)


def _probe_controller(controller):
    """Verify that the cached PCA9685 still answers without moving a servo."""
    if controller is None:
        return False
    try:
        # Channel 15 is not assigned to a TARS servo. Writing zero verifies
        # the I2C path without energizing any mechanism.
        with _pwm_io_lock:
            controller.channels[PCA_PROBE_CHANNEL].duty_cycle = 0
        return True
    except Exception as exc:
        queue_message(f"WARNING: PCA9685 health probe failed: {_describe_hardware_error(exc)}")
        return False


def _discard_controller(reason=None):
    """Forget and close a controller that can no longer be trusted."""
    global pca, _i2c, _channels_initialized

    with _hardware_lifecycle_lock:
        controller = pca
        i2c_bus = _i2c
        pca = None
        _i2c = None
        _channels_initialized.clear()

        if controller is not None:
            try:
                controller.deinit()
            except Exception:
                pass
        if i2c_bus is not None:
            try:
                i2c_bus.deinit()
            except Exception:
                pass

    if reason:
        queue_message(f"SERVO: Controller connection was reset: {reason}")

def set_battery_module(battery_mod):
    global battery_module
    battery_module = battery_mod

def signal_servo_activity():
    if battery_module is not None:
        battery_module.signal_servo_activity()

def initialize_pca9685(retries=MAX_RETRIES, retry_delay=0.35):
    """Open the PCA9685 with bounded retries.

    A Raspberry Pi can briefly report an I2C error while a previous process is
    releasing the bus or while the controller power rail settles.  The old
    implementation tried once during import and left movement disabled for the
    rest of the process.  Only publish fully initialized objects here so a
    failed attempt cannot leave a half-open controller behind.
    """
    global pca, _i2c, _channels_initialized

    attempts = max(1, int(retries))
    with _hardware_lifecycle_lock:
        if pca is not None:
            if _probe_controller(pca):
                return True
            _discard_controller("cached controller did not answer its health probe")

        last_error = None
        for attempt in range(1, attempts + 1):
            candidate_i2c = None
            candidate_pca = None
            try:
                candidate_i2c = busio.I2C(board.SCL, board.SDA)
                candidate_pca = PCA9685(candidate_i2c, address=0x40)
                candidate_pca.frequency = 50
                if not _probe_controller(candidate_pca):
                    raise OSError("PCA9685 did not respond after it was opened")
                _i2c = candidate_i2c
                pca = candidate_pca
                _channels_initialized.clear()
                queue_message(
                    f"LOAD: PCA9685 initialized successfully (attempt {attempt}/{attempts})"
                )
                return True
            except Exception as exc:
                last_error = exc
                if candidate_pca is not None:
                    try:
                        candidate_pca.deinit()
                    except Exception:
                        pass
                if candidate_i2c is not None:
                    try:
                        candidate_i2c.deinit()
                    except Exception:
                        pass
                pca = None
                _i2c = None
                _channels_initialized.clear()

                detail = _describe_hardware_error(exc)
                queue_message(
                    f"WARNING: PCA9685 initialization attempt {attempt}/{attempts} failed: {detail}"
                )
                if attempt < attempts:
                    time.sleep(max(0.0, float(retry_delay)))

        queue_message(
            f"ERROR: PCA9685 unavailable after {attempts} attempts: {last_error}"
        )
        return False


def ensure_servo_hardware():
    """Return True when movement may safely write to the PCA9685.

    This gives a later voice command one recovery attempt when startup saw a
    transient I2C failure, without moving or energizing any servo by itself.
    """
    if _emergency_stop_event.is_set():
        queue_message("MOVEMENT: Emergency power-off is latched; reset it before moving")
        return False
    if _hardware_handoff_event.is_set():
        return False
    if pca is not None:
        with _hardware_lifecycle_lock:
            if _probe_controller(pca):
                return True
            _discard_controller("controller stopped responding before movement")

    controls = config.get("CONTROLS", {})
    if not (controls.get("enabled", False) or controls.get("voicemovement", False)):
        queue_message("MOVEMENT: Servo control is disabled in config.ini")
        return False

    queue_message("SERVO: Controller offline; attempting recovery before movement")
    recovered = initialize_pca9685()
    if recovered:
        queue_message("SERVO: Controller recovery succeeded")
    return recovered

controls = config.get('CONTROLS', {})
_movement_enabled = controls.get('enabled', False) or controls.get('voicemovement', False)
# Hardware is opened by initialize_servos() during the managed runtime startup.
# Keeping module import side-effect free prevents the standalone servo tester
# from accidentally opening a second controller before it creates its own.

leftMainMin = int(config["SERVO"]["leftMainMin"])
leftMainMax = int(config["SERVO"]["leftMainMax"])
leftForarmMin = int(config["SERVO"]["leftForarmMin"])
leftForarmMax = int(config["SERVO"]["leftForarmMax"])
leftHandMin = int(config["SERVO"]["leftHandMin"])
leftHandMax = int(config["SERVO"]["leftHandMax"])

rightMainMin = int(config["SERVO"]["rightMainMin"])
rightMainMax = int(config["SERVO"]["rightMainMax"])
rightForarmMin = int(config["SERVO"]["rightForarmMin"])
rightForarmMax = int(config["SERVO"]["rightForarmMax"])
rightHandMin = int(config["SERVO"]["rightHandMin"])
rightHandMax = int(config["SERVO"]["rightHandMax"])

leftMainOffset = int(config["SERVO"]["leftMainOffset"])
leftMainMin = leftMainMin + leftMainOffset
leftMainMax = leftMainMax + leftMainOffset

leftForearmOffset = int(config["SERVO"]["leftForearmOffset"])
leftForarmMin = leftForarmMin + leftForearmOffset
leftForarmMax = leftForarmMax + leftForearmOffset

leftHandOffset = int(config["SERVO"]["leftHandOffset"])
leftHandMin = leftHandMin + leftHandOffset
leftHandMax = leftHandMax + leftHandOffset

rightMainOffset = int(config["SERVO"]["rightMainOffset"])
rightMainMin = rightMainMin + rightMainOffset
rightMainMax = rightMainMax + rightMainOffset

rightForearmOffset = int(config["SERVO"]["rightForearmOffset"])
rightForarmMin = rightForarmMin + rightForearmOffset
rightForarmMax = rightForarmMax + rightForearmOffset

rightHandOffset = int(config["SERVO"]["rightHandOffset"])
rightHandMin = rightHandMin + rightHandOffset
rightHandMax = rightHandMax + rightHandOffset

perfectLeftHeightOffset = int(config["SERVO"]["perfectLeftHeightOffset"])
leftUpHeight = int(config["SERVO"]["leftUpHeight"]) + perfectLeftHeightOffset
leftNeutralHeight = NEUTRAL_LEFT_HEIGHT + perfectLeftHeightOffset
leftDownHeight = int(config["SERVO"]["leftDownHeight"]) + perfectLeftHeightOffset

perfectRightHeightOffset = int(config["SERVO"]["perfectRightHeightOffset"])
rightUpHeight = int(config["SERVO"]["rightUpHeight"]) - perfectRightHeightOffset
rightNeutralHeight = NEUTRAL_RIGHT_HEIGHT - perfectRightHeightOffset
rightDownHeight = int(config["SERVO"]["rightDownHeight"]) - perfectRightHeightOffset

perfectLeftLegOffset = int(config["SERVO"]["perfectLeftLegOffset"])
forwardLeftLeg = int(config["SERVO"]["forwardLeftLeg"]) + perfectLeftLegOffset
neutralLeftLeg = NEUTRAL_LEFT_LEG + perfectLeftLegOffset
backLeftLeg = int(config["SERVO"]["backLeftLeg"]) + perfectLeftLegOffset

perfectRightLegOffset = int(config["SERVO"]["perfectRightLegOffset"])
forwardRightLeg = int(config["SERVO"]["forwardRightLeg"]) + perfectRightLegOffset
neutralRightLeg = NEUTRAL_RIGHT_LEG + perfectRightLegOffset
backRightLeg = int(config["SERVO"]["backRightLeg"]) + perfectRightLegOffset

MOVING = False
HOLD = -1
ARMS_PRESENT = config["SERVO"]["arms_present"]

if not servo_positions:
    print("[SERVO] No saved positions - initializing to neutral estimates")
    servo_positions[0] = leftNeutralHeight
    servo_positions[1] = rightNeutralHeight
    servo_positions[2] = neutralLeftLeg
    servo_positions[3] = neutralRightLeg
    servo_positions[4] = leftMainMin
    servo_positions[5] = leftForarmMin
    servo_positions[6] = leftHandMin
    servo_positions[7] = rightMainMin
    servo_positions[8] = rightForarmMin
    servo_positions[9] = rightHandMin
else:
    print("[SERVO] Loaded saved positions", flush=True)

_on_movement_start = None
_on_movement_end = None
_is_ventilate_operation = False


def refresh_config():
    """Re-read config and update all offset-dependent servo variables without reinitializing PCA."""
    global config
    global leftMainMin, leftMainMax, leftForarmMin, leftForarmMax, leftHandMin, leftHandMax
    global rightMainMin, rightMainMax, rightForarmMin, rightForarmMax, rightHandMin, rightHandMax
    global leftMainOffset, leftForearmOffset, leftHandOffset
    global rightMainOffset, rightForearmOffset, rightHandOffset
    global perfectLeftHeightOffset, leftUpHeight, leftNeutralHeight, leftDownHeight
    global perfectRightHeightOffset, rightUpHeight, rightNeutralHeight, rightDownHeight
    global perfectLeftLegOffset, forwardLeftLeg, neutralLeftLeg, backLeftLeg
    global perfectRightLegOffset, forwardRightLeg, neutralRightLeg, backRightLeg
    global ARMS_PRESENT, MOVEMENT_WATCHDOG_ENABLED
    global MOVEMENT_WATCHDOG_TIMEOUT, MOVEMENT_STALL_TIMEOUT

    cfg = load_config()
    config = cfg
    servo = cfg["SERVO"]

    # Arm base values
    leftMainMin = int(servo["leftMainMin"])
    leftMainMax = int(servo["leftMainMax"])
    leftForarmMin = int(servo["leftForarmMin"])
    leftForarmMax = int(servo["leftForarmMax"])
    leftHandMin = int(servo["leftHandMin"])
    leftHandMax = int(servo["leftHandMax"])
    rightMainMin = int(servo["rightMainMin"])
    rightMainMax = int(servo["rightMainMax"])
    rightForarmMin = int(servo["rightForarmMin"])
    rightForarmMax = int(servo["rightForarmMax"])
    rightHandMin = int(servo["rightHandMin"])
    rightHandMax = int(servo["rightHandMax"])

    # Arm offsets
    leftMainOffset = int(servo["leftMainOffset"])
    leftMainMin += leftMainOffset
    leftMainMax += leftMainOffset
    leftForearmOffset = int(servo["leftForearmOffset"])
    leftForarmMin += leftForearmOffset
    leftForarmMax += leftForearmOffset
    leftHandOffset = int(servo["leftHandOffset"])
    leftHandMin += leftHandOffset
    leftHandMax += leftHandOffset
    rightMainOffset = int(servo["rightMainOffset"])
    rightMainMin += rightMainOffset
    rightMainMax += rightMainOffset
    rightForearmOffset = int(servo["rightForearmOffset"])
    rightForarmMin += rightForearmOffset
    rightForarmMax += rightForearmOffset
    rightHandOffset = int(servo["rightHandOffset"])
    rightHandMin += rightHandOffset
    rightHandMax += rightHandOffset

    # Leg offsets
    perfectLeftHeightOffset = int(servo["perfectLeftHeightOffset"])
    leftUpHeight = int(servo["leftUpHeight"]) + perfectLeftHeightOffset
    leftNeutralHeight = NEUTRAL_LEFT_HEIGHT + perfectLeftHeightOffset
    leftDownHeight = int(servo["leftDownHeight"]) + perfectLeftHeightOffset

    perfectRightHeightOffset = int(servo["perfectRightHeightOffset"])
    rightUpHeight = int(servo["rightUpHeight"]) - perfectRightHeightOffset
    rightNeutralHeight = NEUTRAL_RIGHT_HEIGHT - perfectRightHeightOffset
    rightDownHeight = int(servo["rightDownHeight"]) - perfectRightHeightOffset

    perfectLeftLegOffset = int(servo["perfectLeftLegOffset"])
    forwardLeftLeg = int(servo["forwardLeftLeg"]) + perfectLeftLegOffset
    neutralLeftLeg = NEUTRAL_LEFT_LEG + perfectLeftLegOffset
    backLeftLeg = int(servo["backLeftLeg"]) + perfectLeftLegOffset

    perfectRightLegOffset = int(servo["perfectRightLegOffset"])
    forwardRightLeg = int(servo["forwardRightLeg"]) + perfectRightLegOffset
    neutralRightLeg = NEUTRAL_RIGHT_LEG + perfectRightLegOffset
    backRightLeg = int(servo["backRightLeg"]) + perfectRightLegOffset

    ARMS_PRESENT = servo["arms_present"]
    MOVEMENT_WATCHDOG_ENABLED = bool(
        servo.get("movement_watchdog_enabled", True)
    )
    MOVEMENT_WATCHDOG_TIMEOUT = float(
        servo.get("movement_watchdog_timeout", 45.0)
    )
    MOVEMENT_STALL_TIMEOUT = float(
        servo.get("movement_stall_timeout", 8.0)
    )


def set_movement_callbacks(on_start=None, on_end=None):

    global _on_movement_start, _on_movement_end
    _on_movement_start = on_start
    _on_movement_end = on_end

def _notify_movement_start():
    global _is_ventilate_operation

    signal_servo_activity()

    if not _is_ventilate_operation:
        try:
            from modules.module_cputemp import is_ventilating
            if is_ventilating():
                from modules.module_movements import ventilate_off
                ventilate_off()
        except Exception as e:
            pass

    if _on_movement_start:
        try:
            _on_movement_start()
        except Exception as e:
            queue_message(f"ERROR: Failed to pause UI/STT: {e}")

def _notify_movement_end():

    signal_servo_activity()

    if _on_movement_end:
        try:
            _on_movement_end()
        except Exception as e:
            queue_message(f"ERROR: Failed to resume UI/STT: {e}")

def pulse_to_duty_cycle(pulse_value):
    
    MAX_PULSE = 600
    pulse_us = 500 + (pulse_value / MAX_PULSE) * 2000
    duty_cycle = int((pulse_us / 20000.0) * 65535)
    return duty_cycle


def get_servo_channel_bounds(channel):
    """Return the calibrated mechanical envelope for a TARS servo channel."""
    ranges = {
        0: (leftUpHeight, leftNeutralHeight, leftDownHeight),
        1: (rightUpHeight, rightNeutralHeight, rightDownHeight),
        2: (forwardLeftLeg, neutralLeftLeg, backLeftLeg),
        3: (forwardRightLeg, neutralRightLeg, backRightLeg),
        4: (leftMainMin, leftMainMax),
        5: (leftForarmMin, leftForarmMax),
        6: (leftHandMin, leftHandMax),
        7: (rightMainMin, rightMainMax),
        8: (rightForarmMin, rightForarmMax),
        9: (rightHandMin, rightHandMax),
    }
    values = ranges.get(channel)
    if values is None:
        return None
    return max(SERVO_MIN_PULSE, min(values)), min(SERVO_MAX_PULSE, max(values))


def _validate_servo_write(channel, pwm_value, enforce_calibrated_bounds=True):
    """Validate the final hardware command at the last boundary before I2C."""
    if isinstance(channel, bool) or not isinstance(channel, Integral):
        queue_message(f"ERROR: Refused servo write with invalid channel {channel!r}")
        return None
    channel = int(channel)
    bounds = get_servo_channel_bounds(channel)
    if bounds is None:
        queue_message(
            f"ERROR: Refused servo write to unassigned channel {channel}; "
            "TARS servo channels are 0-9"
        )
        return None

    if isinstance(pwm_value, bool) or not isinstance(pwm_value, Real):
        queue_message(
            f"ERROR: Refused non-numeric PWM value {pwm_value!r} on channel {channel}"
        )
        return None
    numeric_value = float(pwm_value)
    if not math.isfinite(numeric_value) or not numeric_value.is_integer():
        queue_message(
            f"ERROR: Refused non-integer PWM value {pwm_value!r} on channel {channel}"
        )
        return None
    pwm_value = int(numeric_value)
    if not SERVO_MIN_PULSE <= pwm_value <= SERVO_MAX_PULSE:
        queue_message(
            f"ERROR: Refused unsafe PWM value {pwm_value} on channel {channel}; "
            f"controller range is {SERVO_MIN_PULSE}-{SERVO_MAX_PULSE}"
        )
        return None

    if enforce_calibrated_bounds:
        minimum, maximum = bounds
        if not minimum <= pwm_value <= maximum:
            # A saved position can legitimately predate the current offsets.
            # Refusing every out-of-envelope intermediate value would strand
            # that joint at the stale position: it could not travel back into
            # the newly calibrated range. Permit only monotonic recovery toward
            # the nearest boundary. A joint already inside its envelope can
            # never use this exception to travel outside it.
            current = servo_positions.get(channel)
            recovering_low = (
                isinstance(current, Real)
                and current < minimum
                and current < pwm_value < minimum
            )
            recovering_high = (
                isinstance(current, Real)
                and current > maximum
                and maximum < pwm_value < current
            )
            if not (recovering_low or recovering_high):
                queue_message(
                    f"ERROR: Refused PWM value {pwm_value} on channel {channel}; "
                    f"calibrated range is {minimum}-{maximum}"
                )
                return None
    return channel, pwm_value


def _write_servo_pwm_unlocked(channel, pwm_value):
    global _channels_initialized

    if (
        pca is None
        or _hardware_handoff_event.is_set()
        or _emergency_stop_event.is_set()
    ):
        return False

    controller = pca
    duty_cycle = pulse_to_duty_cycle(pwm_value)
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            if _emergency_stop_event.is_set():
                return False
            with _pwm_io_lock:
                if _emergency_stop_event.is_set():
                    return False
                controller.channels[channel].duty_cycle = duty_cycle
            _channels_initialized.add(channel)
            _confirm_servo_write()
            return True

        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(0.05 * (attempt + 1))

    detail = _describe_hardware_error(last_error)
    queue_message(
        f"ERROR: Servo write failed on channel {channel} after "
        f"{MAX_RETRIES} attempts: {detail}"
    )

    # The failed target may have occurred after several joints were already
    # energized. Deinitializing the Python driver does not guarantee that the
    # PCA9685 stops generating the last programmed PWM signal, so first make a
    # bounded, best-effort attempt to release every output on the still-open
    # controller. This is especially important after a transient I2C error in
    # the middle of a gesture.
    failed_release_channels = _disable_controller_outputs(controller)
    if failed_release_channels:
        queue_message(
            "CRITICAL: Unable to release PWM on servo channel(s) "
            f"{', '.join(str(value) for value in failed_release_channels)}; "
            "switch servo power off before touching TARS"
        )
    with _hardware_lifecycle_lock:
        if pca is controller:
            _discard_controller(f"PWM write failure on channel {channel}")
    return False


def _write_validated_servo_pwm(channel, pwm_value):
    """Serialize even direct low-level writes with the movement owner."""
    if _emergency_stop_event.is_set():
        queue_message(
            f"ERROR: Refused servo write on channel {channel}; "
            "emergency power-off is latched"
        )
        return False
    if not _movement_command_lock.acquire(timeout=SERVO_WRITE_LOCK_TIMEOUT):
        queue_message(
            f"ERROR: Refused servo write on channel {channel}; "
            "another movement owns the controller"
        )
        return False
    try:
        return _write_servo_pwm_unlocked(channel, pwm_value)
    finally:
        _movement_command_lock.release()


def set_servo_pwm(channel, pwm_value):
    """Write only within the servo's currently calibrated mechanical range."""
    validated = _validate_servo_write(channel, pwm_value)
    if validated is None:
        return False
    return _write_validated_servo_pwm(*validated)


def set_calibration_servo_pwm(channel, pwm_value):
    """Calibration-only write bounded by assigned channels and controller limits.

    A calibrator must be able to explore a prospective envelope that is not
    saved yet.  It still cannot address an unassigned channel or leave the
    absolute safe PWM range.  The QML tester performs its own endpoint checks
    and ramps to every prospective target before using this explicit API.
    """
    validated = _validate_servo_write(
        channel, pwm_value, enforce_calibrated_bounds=False
    )
    if validated is None:
        return False
    return _write_validated_servo_pwm(*validated)

def initialize_servos(startup_attempts=2):
    """Validate the controller and perform a bounded, retryable startup pose."""
    global MOVING

    controls = config.get('CONTROLS', {})
    movement_enabled = controls.get('enabled', False) or controls.get('voicemovement', False)
    if not movement_enabled:
        queue_message("SERVO: Movement control is disabled in config.ini")
        return False

    attempts = max(1, int(startup_attempts))
    _movement_stop_event.clear()
    MOVING = False

    for attempt in range(1, attempts + 1):
        try:
            if not ensure_servo_hardware():
                raise RuntimeError("PCA9685 is unavailable")

            controller = pca
            for channel in range(16):
                controller.channels[channel].duty_cycle = 0
            _channels_initialized.clear()
            time.sleep(0.1)

            # Gently re-engage servos at their saved positions before moving
            # to neutral. Refuse corrupt or unsafe saved values.
            for channel, value in servo_positions.items():
                channel = int(channel)
                value = int(value)
                if not 0 <= channel < 16:
                    continue
                if not SERVO_MIN_PULSE <= value <= SERVO_MAX_PULSE:
                    raise ValueError(
                        f"Unsafe saved PWM value {value} on channel {channel}"
                    )
                if not set_servo_pwm(channel, value):
                    raise RuntimeError(
                        f"Could not restore saved position on channel {channel}"
                    )
                time.sleep(0.02)
            if servo_positions:
                time.sleep(0.3)

            reset_positions()
            if not ensure_servo_hardware():
                raise RuntimeError("PCA9685 failed its post-startup health check")

            queue_message(
                "SYSTEM: Servo readiness check passed; all PWM outputs returned to idle"
            )
            return True
        except Exception as exc:
            queue_message(
                f"WARNING: Servo startup attempt {attempt}/{attempts} failed: {exc}"
            )
            disable_all_servos()
            _discard_controller("startup readiness check failed")
            MOVING = False
            if attempt < attempts:
                time.sleep(0.5)

    queue_message(
        "ERROR: Servo startup failed. Movement remains offline until the "
        "controller passes an automatic recovery check."
    )
    return False

def _disable_controller_outputs(controller, attempts=3):
    """Best-effort PWM release that never abandons later channels.

    A single transient I2C failure used to abort the entire 16-channel loop.
    If (for example) channel 8 failed, channels 9-15 were never told to stop.
    Retry only the channels that failed while continuing to release every
    other output. Return the channels that could not be confirmed off.
    """
    if controller is None:
        return []

    pending = list(range(16))
    last_errors = {}
    # Emergency release bypasses the movement command lock, but it must not
    # interleave register writes with the one I2C transaction already in
    # flight. Once this short bus lock is acquired, the emergency latch blocks
    # the movement thread from issuing another non-zero write.
    with _pwm_io_lock:
        for attempt in range(max(1, int(attempts))):
            failed = []
            for channel in pending:
                try:
                    controller.channels[channel].duty_cycle = 0
                    last_errors.pop(channel, None)
                except Exception as exc:
                    failed.append(channel)
                    last_errors[channel] = exc
            pending = failed
            if not pending:
                return []
            if attempt < attempts - 1:
                time.sleep(0.03 * (attempt + 1))

    for channel in pending:
        queue_message(
            f"ERROR: Could not disable servo channel {channel}: "
            f"{_describe_hardware_error(last_errors[channel])}"
        )
    return pending


def disable_all_servos():
    global _channels_initialized

    if pca is None:
        _channels_initialized.clear()
        return True

    failed_channels = _disable_controller_outputs(pca)
    _channels_initialized.intersection_update(failed_channels)
    time.sleep(0.05)
    return not failed_channels


def _deinitialize_pca9685():
    """Disable PWM and close the controller and I2C bus without moving."""
    global pca, _i2c, _channels_initialized

    with _hardware_lifecycle_lock:
        controller = pca
        i2c_bus = _i2c
        if controller is not None:
            disable_all_servos()
        pca = None
        _i2c = None
        _channels_initialized.clear()

        if controller is not None:
            try:
                controller.deinit()
            except Exception as exc:
                queue_message(f"WARNING: PCA9685 deinitialization reported: {exc}")
        if i2c_bus is not None:
            try:
                i2c_bus.deinit()
            except Exception:
                pass


def release_hardware_for_calibration(timeout=8.0):
    """Safely release the PCA9685 so a standalone calibrator can own it.

    New movement commands are rejected before the current movement is asked to
    stop.  Taking the movement lock ensures that no in-process motion can still
    be writing PWM when the controller is disabled and deinitialized.
    """
    global pca, _channels_initialized

    if _hardware_handoff_event.is_set():
        return False

    _hardware_handoff_event.set()
    request_controlled_stop("Stopping movement for servo calibration")
    acquired = _movement_command_lock.acquire(timeout=max(0.1, float(timeout)))
    if not acquired:
        emergency_power_off(
            "Calibration handoff timed out waiting for movement",
            source="calibration handoff",
        )
        _hardware_handoff_event.clear()
        queue_message("ERROR: Servo calibration handoff timed out waiting for movement to stop")
        return False

    try:
        _deinitialize_pca9685()
        queue_message("SERVO: PCA9685 released for calibration; PWM outputs are disabled")
        return True
    except Exception as exc:
        queue_message(f"ERROR: Unable to release PCA9685 for calibration: {exc}")
        _hardware_handoff_event.clear()
        return False
    finally:
        _movement_command_lock.release()


def reclaim_hardware_after_calibration():
    """Reopen the PCA9685 after calibration without energizing any servo."""
    global pca

    try:
        # The tester may have saved new offsets in config.ini.  Invalidate the
        # process-local config cache before refreshing module constants.
        from modules import module_config

        module_config._config_cache = None
        refresh_config()
        controls = config.get("CONTROLS", {})
        movement_enabled = controls.get("enabled", False) or controls.get("voicemovement", False)
        if not movement_enabled:
            pca = None
            queue_message("SERVO: Calibration closed; movement control remains disabled by configuration")
            return True

        if not initialize_pca9685():
            queue_message("ERROR: PCA9685 could not be reclaimed after calibration")
            return False

        # Reopening the controller must never cause an automatic pose change.
        # Keep every channel torque-free until the next explicit movement.
        disable_all_servos()
        queue_message("SERVO: PCA9685 reclaimed after calibration; PWM outputs remain disabled")
        return True
    finally:
        _hardware_handoff_event.clear()

def reset_positions():
    global servo_positions

    move_legs(20, 20, None, None, 0.6)

    # Use saved positions as starting points (don't overwrite them)
    # This ensures smooth movement from last known position to neutral
    neutral_defaults = {
        0: leftNeutralHeight,
        1: rightNeutralHeight,
        2: neutralLeftLeg,
        3: neutralRightLeg,
        4: leftMainMin,
        5: leftForarmMin,
        6: leftHandMin,
        7: rightMainMin,
        8: rightForarmMin,
        9: rightHandMin,
    }
    for ch, val in neutral_defaults.items():
        if ch not in servo_positions:
            servo_positions[ch] = val

    disable_all_servos()
    move_legs(30, 30, 50, 50, 0.5)
    wait_for_movement(0.2)
    move_legs(50, 50, 50, 50, 0.5)
    wait_for_movement(0.3)

    move_arm(1, 1, 1, 1, 1, 1, 0.3)
    wait_for_movement(0.5)

    disable_all_servos()


def execute_direct_servo_command(name, command):
    """Run a WebUI/manual servo operation through the shared movement gate.

    Direct leg and arm controls used to bypass the movement lock, hardware
    readiness check, lifecycle callbacks, and error recovery. This adapter
    gives those operations the same guarantees as named movement presets.
    """
    if not callable(command):
        _record_movement_failure(name, "Servo command is not callable")
        return False

    def direct_command():
        global MOVING

        MOVING = True
        _notify_movement_start()
        try:
            result = command()
            return result is not False
        finally:
            MOVING = False
            _notify_movement_end()

    direct_command.__name__ = str(name or "direct_servo_command")
    return movement_command(direct_command)()


def begin_direct_servo_session(name):
    """Begin a manually scoped direct-servo command on the current thread."""
    global MOVING

    if _emergency_stop_event.is_set():
        _record_movement_failure(
            name, _emergency_stop_reason or "Emergency power-off is latched"
        )
        return False
    if _hardware_handoff_event.is_set():
        _record_movement_failure(name, "Hardware is reserved for servo calibration")
        return False
    if not _movement_command_lock.acquire(timeout=MOVEMENT_LOCK_TIMEOUT):
        _record_movement_failure(name, "Timed out waiting for the movement lock")
        return False

    try:
        _movement_stop_event.clear()
        if MOVING:
            _record_movement_failure(name, "Another movement is still active")
            _movement_command_lock.release()
            return False
        if not ensure_servo_hardware():
            _record_movement_failure(name, "Servo controller unavailable")
            _movement_command_lock.release()
            return False

        idle_remaining = (
            MOVEMENT_MIN_IDLE_SECONDS - (time.monotonic() - _movement_finished_at)
        )
        if idle_remaining > 0 and _movement_stop_event.wait(idle_remaining):
            _record_movement_failure(name, "Movement was stopped")
            _movement_command_lock.release()
            return False

        MOVING = True
        _movement_thread_state.direct_session_name = str(name)
        _movement_thread_state.direct_watchdog = _start_movement_watchdog(name)
        _notify_movement_start()
        return True
    except Exception as exc:
        _record_movement_failure(name, _describe_hardware_error(exc))
        _movement_command_lock.release()
        return False


def end_direct_servo_session(name, success=True, error=None):
    """End a session opened by begin_direct_servo_session()."""
    global MOVING, _movement_finished_at

    active_name = getattr(_movement_thread_state, "direct_session_name", None)
    if active_name is None:
        return False

    try:
        MOVING = False
        _notify_movement_end()
        if (
            success
            and not _movement_stop_event.is_set()
            and not _emergency_stop_event.is_set()
        ):
            _record_movement_success(name)
        else:
            detail = (
                error
                or _emergency_stop_reason
                or _controlled_stop_reason
                or "Movement was stopped"
            )
            _record_movement_failure(name, detail)
            if (
                pca is None
                and not _hardware_handoff_event.is_set()
                and not _emergency_stop_event.is_set()
            ):
                initialize_pca9685(retries=1)
        return bool(success and not _emergency_stop_event.is_set())
    finally:
        _finish_movement_watchdog(
            getattr(_movement_thread_state, "direct_watchdog", None)
        )
        if hasattr(_movement_thread_state, "direct_watchdog"):
            del _movement_thread_state.direct_watchdog
        del _movement_thread_state.direct_session_name
        _movement_finished_at = time.monotonic()
        _movement_command_lock.release()

def move_servos_timed(movements, duration, easing_strength=None):
    """
    Move multiple servos to their targets over a fixed duration at 50 Hz.
    
    Parameters:
    - movements: List of (channel, target_value) tuples
    - duration: Total move duration in seconds
    - easing_strength: Easing amount (None uses global default, 0 = linear, higher = more ease in/out)
    """
    global _channels_initialized

    if _movement_stop_event.is_set():
        raise MovementCancelled()

    effective_easing = easing_strength if easing_strength is not None else global_easing_strength
    effective_easing = max(0.0, min(1.0, float(effective_easing)))
    signal_servo_activity()

    servo_data = []
    hold_channels = []

    for channel, target_value in movements:
        if target_value is None:
            continue

        current_value = servo_positions.get(channel, None)

        if current_value is None:
            neutral_positions = {
                0: leftNeutralHeight,
                1: rightNeutralHeight,
                2: neutralLeftLeg,
                3: neutralRightLeg,
                4: leftMainMin,
                5: leftForarmMin,
                6: leftHandMin,
                7: rightMainMin,
                8: rightForarmMin,
                9: rightHandMin,
            }
            current_value = neutral_positions.get(channel, 300)
            servo_positions[channel] = current_value

        if target_value == -1:
            hold_channels.append((channel, current_value))
            continue

        target_value = int(round(target_value))
        if not SERVO_MIN_PULSE <= target_value <= SERVO_MAX_PULSE:
            raise ValueError(
                f"Unsafe PWM target {target_value} on channel {channel}; "
                f"allowed range is {SERVO_MIN_PULSE}-{SERVO_MAX_PULSE}"
            )
        if current_value == target_value:
            # The channel may have been disabled after this position was saved.
            # Reissue the PWM value so an equal-target move also restores torque.
            if channel not in _channels_initialized:
                if not set_servo_pwm(channel, current_value):
                    raise RuntimeError(f"Unable to energize servo channel {channel}")
            continue

        servo_data.append({
            'channel': channel,
            'start': int(current_value),
            'last': int(current_value),
            'target': target_value,
        })

    for channel, value in hold_channels:
        if not set_servo_pwm(channel, value):
            raise RuntimeError(f"Unable to hold servo channel {channel}")

    if not servo_data:
        return

    try:
        from modules.module_cputemp import record_movement
        record_movement()
    except Exception:
        pass

    duration = max(1.0 / SERVO_UPDATE_HZ, float(duration))
    frame_count = max(1, int(math.ceil(duration * SERVO_UPDATE_HZ)))
    frame_period = duration / frame_count
    started_at = time.monotonic()

    for frame in range(1, frame_count + 1):
        if _movement_stop_event.is_set():
            raise MovementCancelled()

        linear_progress = frame / frame_count
        smooth_progress = linear_progress * linear_progress * (3.0 - 2.0 * linear_progress)
        progress = (
            linear_progress * (1.0 - effective_easing)
            + smooth_progress * effective_easing
        )

        for servo in servo_data:
            value = int(round(servo['start'] + (servo['target'] - servo['start']) * progress))
            if value == servo['last']:
                continue
            if not set_servo_pwm(servo['channel'], value):
                raise RuntimeError(f"Servo write failed on channel {servo['channel']}")
            servo['last'] = value
            servo_positions[servo['channel']] = value

        remaining = started_at + frame * frame_period - time.monotonic()
        if remaining > 0 and _movement_stop_event.wait(remaining):
            raise MovementCancelled()

    for servo in servo_data:
        servo_positions[servo['channel']] = servo['target']

    signal_servo_activity()


def move_servos_synchronized(movements, speed_factor, easing_strength=None):
    """Backward-compatible speed API backed by synchronized timed motion."""
    active = []
    for channel, target_value in movements:
        if target_value is None or target_value == -1:
            continue
        start = servo_positions.get(channel)
        if start is not None:
            active.append(abs(int(round(target_value)) - int(start)))

    max_distance = max(active, default=0)
    speed = max(0.05, min(1.0, float(speed_factor)))
    ticks_per_second = 70.0 + 230.0 * speed
    duration = max(0.10, max_distance / ticks_per_second)
    move_servos_timed(movements, duration, easing_strength=easing_strength)


def move_servos_original(movements, speed_factor, easing_strength=None):
    """Run the original tick-by-tick synchronized movement algorithm.

    The proven original step gait depends on this transition behavior as well
    as its target poses. Safety checks and cooperative cancellation are kept,
    but the stepping, delay curve, and final settling delay match the original
    servotester implementation.
    """
    effective_easing = easing_strength if easing_strength is not None else global_easing_strength
    effective_easing = max(0.0, min(1.0, float(effective_easing)))
    signal_servo_activity()

    servo_data = []
    hold_channels = []
    has_uninitialized_channel = False
    neutral_positions = {
        0: leftNeutralHeight,
        1: rightNeutralHeight,
        2: neutralLeftLeg,
        3: neutralRightLeg,
        4: leftMainMin,
        5: leftForarmMin,
        6: leftHandMin,
        7: rightMainMin,
        8: rightForarmMin,
        9: rightHandMin,
    }

    for channel, target_value in movements:
        if target_value is None:
            continue
        if _movement_stop_event.is_set():
            raise MovementCancelled()

        current_value = int(servo_positions.get(channel, neutral_positions.get(channel, 300)))
        servo_positions[channel] = current_value
        if channel not in _channels_initialized:
            has_uninitialized_channel = True

        if target_value == -1:
            hold_channels.append((channel, current_value))
            continue

        target_value = int(round(target_value))
        if not SERVO_MIN_PULSE <= target_value <= SERVO_MAX_PULSE:
            raise ValueError(
                f"Unsafe PWM target {target_value} on channel {channel}; "
                f"allowed range is {SERVO_MIN_PULSE}-{SERVO_MAX_PULSE}"
            )
        if current_value == target_value:
            if channel not in _channels_initialized and not set_servo_pwm(channel, current_value):
                raise RuntimeError(f"Unable to energize servo channel {channel}")
            continue

        servo_data.append({
            "channel": channel,
            "current": current_value,
            "target": target_value,
            "step": 1 if target_value > current_value else -1,
            "distance": abs(target_value - current_value),
            "steps_taken": 0,
        })

    for channel, value in hold_channels:
        if not set_servo_pwm(channel, value):
            raise RuntimeError(f"Unable to hold servo channel {channel}")

    if not servo_data:
        return

    try:
        from modules.module_cputemp import record_movement
        record_movement()
    except Exception:
        pass

    max_distance = max(item["distance"] for item in servo_data)
    effective_speed = min(float(speed_factor), 0.3) if has_uninitialized_channel else float(speed_factor)
    effective_speed = max(0.0, min(1.0, effective_speed))
    base_delay = 0.02 * (1.0 - effective_speed)

    while any(item["current"] != item["target"] for item in servo_data):
        if _movement_stop_event.is_set():
            raise MovementCancelled()

        for item in servo_data:
            if item["current"] == item["target"]:
                continue
            item["current"] += item["step"]
            if not set_servo_pwm(item["channel"], item["current"]):
                raise RuntimeError(f"Servo write failed on channel {item['channel']}")
            item["steps_taken"] += 1

        progress = (
            min(item["steps_taken"] for item in servo_data) / max_distance
            if max_distance > 0 else 1.0
        )
        if effective_easing > 0:
            if progress < 0.5:
                eased = 2 * progress * progress
            else:
                eased = 1 - 2 * (1 - progress) * (1 - progress)
            delay_multiplier = 1.0 + effective_easing * (1.0 - 4 * (eased - 0.5) ** 2)
        else:
            delay_multiplier = 1.0

        delay = base_delay * delay_multiplier
        if delay > 0 and _movement_stop_event.wait(delay):
            raise MovementCancelled()

    for item in servo_data:
        servo_positions[item["channel"]] = item["target"]
    _save_servo_positions()
    signal_servo_activity()
    wait_for_movement(0.05)


def move_legs_original(left_height_percent=None, right_height_percent=None,
                       left_leg_percent=None, right_leg_percent=None,
                       speed_factor=1.0):
    """Map leg percentages through calibration, then use the original mover."""
    def percentage_to_value(percent, min_val, max_val):
        if percent is None or percent == 0:
            return None
        normalized = (percent - 1) / 99.0
        return int(round(min_val + (max_val - min_val) * normalized))

    movements = [
        (0, percentage_to_value(left_height_percent, leftUpHeight, leftDownHeight)),
        (1, percentage_to_value(right_height_percent, rightUpHeight, rightDownHeight)),
        (2, percentage_to_value(left_leg_percent, forwardLeftLeg, backLeftLeg)),
        (3, percentage_to_value(right_leg_percent, forwardRightLeg, backRightLeg)),
    ]
    move_servos_original(movements, speed_factor)

def move_legs(left_height_percent=None, right_height_percent=None, left_leg_percent=None, right_leg_percent=None, speed_factor=1.0):
    """
    Move leg servos to specified positions.
    
    Parameters:
    - left_height_percent: Left leg height (1-100, None to skip)
    - right_height_percent: Right leg height (1-100, None to skip)
    - left_leg_percent: Left leg forward/back (1-100, None to skip)
    - right_leg_percent: Right leg forward/back (1-100, None to skip)
    - speed_factor: Speed multiplier (0.0-1.0, higher is faster)
    """
    
    def percentage_to_value(percent, min_val, max_val):
        if percent == 0:
            return None
        normalized = (percent - 1) / 99.0
        value = min_val + (max_val - min_val) * normalized
        return int(round(value))

    movements = []
    
    if left_height_percent is not None and left_height_percent != 0:
        target_value = percentage_to_value(left_height_percent, leftUpHeight, leftDownHeight)
        movements.append((0, target_value))
    
    if right_height_percent is not None and right_height_percent != 0:
        target_value = percentage_to_value(right_height_percent, rightUpHeight, rightDownHeight)
        movements.append((1, target_value))
    
    if left_leg_percent is not None and left_leg_percent != 0:
        target_value = percentage_to_value(left_leg_percent, forwardLeftLeg, backLeftLeg)
        movements.append((2, target_value))
    
    if right_leg_percent is not None and right_leg_percent != 0:
        target_value = percentage_to_value(right_leg_percent, forwardRightLeg, backRightLeg)
        movements.append((3, target_value))

    move_servos_synchronized(movements, speed_factor)


def move_legs_timed(left_height_percent=None, right_height_percent=None,
                    left_leg_percent=None, right_leg_percent=None,
                    duration=0.3, easing_strength=None):
    """Move the four leg servos as one coordinated, duration-based pose."""
    def percentage_to_value(percent, min_val, max_val):
        if percent is None or percent == 0:
            return None
        normalized = (percent - 1) / 99.0
        return int(round(min_val + (max_val - min_val) * normalized))

    movements = [
        (0, percentage_to_value(left_height_percent, leftUpHeight, leftDownHeight)),
        (1, percentage_to_value(right_height_percent, rightUpHeight, rightDownHeight)),
        (2, percentage_to_value(left_leg_percent, forwardLeftLeg, backLeftLeg)),
        (3, percentage_to_value(right_leg_percent, forwardRightLeg, backRightLeg)),
    ]
    move_servos_timed(movements, duration, easing_strength=easing_strength)

def move_arm(left_main=None, left_forearm=None, left_hand=None,
             right_main=None, right_forearm=None, right_hand=None, speed_factor=1.0):
    """
    Move arm servos to specified positions.
    
    Parameters:
    - left_main: Left main arm position (1-100, None to skip, -1 to hold)
    - left_forearm: Left forearm position (1-100, None to skip, -1 to hold)
    - left_hand: Left hand position (1-100, None to skip, -1 to hold)
    - right_main: Right main arm position (1-100, None to skip, -1 to hold)
    - right_forearm: Right forearm position (1-100, None to skip, -1 to hold)
    - right_hand: Right hand position (1-100, None to skip, -1 to hold)
    - speed_factor: Speed multiplier (0.0-1.0, higher is faster)
    """
    
    arm_speed_curve = 0.2
    adjusted_speed = speed_factor ** arm_speed_curve
    arm_easing_strength = 0.85
    
    def percentage_to_value(percent, min_val, max_val):
        if percent == 0:
            return None
        if percent == -1:
            return -1
        if percent == 1:
            return min_val
        if percent == 100:
            return max_val
        if max_val > min_val:
            value = min_val + ((max_val - min_val) * (percent - 1) / 99)
        else:
            value = min_val - ((min_val - max_val) * (percent - 1) / 99)
        return int(round(value))

    def get_value(val, min_val, max_val):
        if val is None or val == 0:
            return None
        if val == -1:
            return -1
        return percentage_to_value(val, min_val, max_val)

    movements = [
        (4, get_value(left_main, leftMainMin, leftMainMax)),
        (5, get_value(left_forearm, leftForarmMin, leftForarmMax)),
        (6, get_value(left_hand, leftHandMin, leftHandMax)),
        (7, get_value(right_main, rightMainMin, rightMainMax)),
        (8, get_value(right_forearm, rightForarmMin, rightForarmMax)),
        (9, get_value(right_hand, rightHandMin, rightHandMax)),
    ]

    move_servos_synchronized(movements, adjusted_speed, easing_strength=arm_easing_strength)


def move_arm_timed(left_main=None, left_forearm=None, left_hand=None,
                   right_main=None, right_forearm=None, right_hand=None,
                   duration=0.5, easing_strength=0.9):
    """Move selected arm joints over an explicit duration.

    The legacy arm speed curve intentionally makes gestures snappy, but it is
    unsuitable for power-sensitive transitions involving several large
    servos. This API lets demanding routines stagger joints and cap their
    acceleration without changing the behavior of every existing gesture.
    """
    def percentage_to_value(percent, min_val, max_val):
        if percent is None or percent == 0:
            return None
        if percent == -1:
            return -1
        normalized = (float(percent) - 1.0) / 99.0
        return int(round(min_val + (max_val - min_val) * normalized))

    movements = [
        (4, percentage_to_value(left_main, leftMainMin, leftMainMax)),
        (5, percentage_to_value(left_forearm, leftForarmMin, leftForarmMax)),
        (6, percentage_to_value(left_hand, leftHandMin, leftHandMax)),
        (7, percentage_to_value(right_main, rightMainMin, rightMainMax)),
        (8, percentage_to_value(right_forearm, rightForarmMin, rightForarmMax)),
        (9, percentage_to_value(right_hand, rightHandMin, rightHandMax)),
    ]
    move_servos_timed(
        movements,
        duration=max(0.10, float(duration)),
        easing_strength=easing_strength,
    )

def cleanup(timeout=8.0):
    """Stop active motion and explicitly release PCA9685 ownership."""
    _hardware_handoff_event.set()
    request_controlled_stop("Application shutdown requested")
    acquired = _movement_command_lock.acquire(timeout=max(0.1, float(timeout)))
    if not acquired:
        emergency_power_off(
            "Shutdown timed out waiting for active movement",
            source="runtime shutdown",
        )
        queue_message("ERROR: Timed out waiting for active movement during servo shutdown")
        return False
    try:
        _deinitialize_pca9685()
        queue_message("SERVO: PCA9685 shutdown complete; PWM outputs are disabled")
        return True
    finally:
        _movement_command_lock.release()

from modules.module_movements import (
    step_forward,
    walk_forward,
    step_backward,
    walk_backward,
    turn_right,
    turn_right_slow,
    turn_left,
    turn_left_slow,
    right_hi,
    left_hi,
    laugh,
    excited,
    swing_legs,
    left_pezz_dispenser,
    right_pezz_dispenser,
    monster,
    pose,
    bow,
    tilt_right,
    tilt_left,
    side_side,
    wave_right,
    wave_left,
    neutral_legs,
    ventilate_on,
    ventilate_off,
    set_swap_turn_directions,
    left_point,
    right_point,
    left_poke,
    right_poke,
    left_wave_open,
    right_wave_open,
    left_handshake,
    right_handshake,
    left_shy_wave,
    right_shy_wave,
    happy_dance
)

set_swap_turn_directions(config["CONTROLS"]["swap_turn_directions"])

from modules.module_movement_registry import (
    MOVEMENTS,
    LEGS_ONLY,
    HAS_ARMS,
    get_all,
    get_by_type,
    get_legs_only,
    get_has_arms,
    get_names,
    get_names_by_type,
    resolve_name
)


def execute_registered_movement(name):
    """Execute a named movement through the one shared reliability path."""
    canonical_name = resolve_name(name)
    if canonical_name == "stop":
        return request_controlled_stop("Voice or controller stop command")
    if canonical_name == "reset_positions":
        return execute_direct_servo_command("reset_positions", reset_positions)
    if canonical_name not in MOVEMENTS:
        _record_movement_failure(canonical_name, "Unknown movement")
        queue_message(f"ERROR: MOVEMENT: Unknown movement '{canonical_name}'")
        return False
    if MOVEMENTS[canonical_name]["type"] == HAS_ARMS and not ARMS_PRESENT:
        message = "Movement requires arms, but arms_present is disabled"
        _record_movement_failure(canonical_name, message)
        queue_message(f"ERROR: MOVEMENT: {message}: {canonical_name}")
        return False

    movement_function = globals().get(canonical_name)
    if not callable(movement_function):
        _record_movement_failure(canonical_name, "Movement implementation is missing")
        queue_message(
            f"ERROR: MOVEMENT: No implementation found for '{canonical_name}'"
        )
        return False
    return bool(movement_function())

if __name__ == "__main__":
    initialize_servos()
