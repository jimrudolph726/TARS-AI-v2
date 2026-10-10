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
_movement_command_lock = threading.RLock()


class MovementCancelled(RuntimeError):
    """Raised internally when an active movement is asked to stop."""


def request_movement_stop():
    """Request a prompt, cooperative stop of the active movement."""
    _movement_stop_event.set()


def movement_stop_requested():
    return _movement_stop_event.is_set()


def movement_command(function):
    """Serialize public movement commands and make them cancellable.

    Existing movement functions already own the MOVING flag and lifecycle
    callbacks.  This wrapper adds the missing cross-thread lock without
    changing their public API.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not _movement_command_lock.acquire(blocking=False):
            queue_message(f"MOVEMENT: Busy; ignored {function.__name__}")
            return False
        _movement_stop_event.clear()
        try:
            function(*args, **kwargs)
            return not _movement_stop_event.is_set()
        except MovementCancelled:
            queue_message(f"MOVEMENT: Stopped {function.__name__}")
            return False
        finally:
            _movement_command_lock.release()
    return wrapped


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
MAX_RETRIES = 3

battery_module = None

def set_battery_module(battery_mod):
    global battery_module
    battery_module = battery_mod

def signal_servo_activity():
    if battery_module is not None:
        battery_module.signal_servo_activity()

def initialize_pca9685():
    
    global pca, _channels_initialized
    
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c, address=0x40)
        pca.frequency = 50
        _channels_initialized.clear()
        queue_message("LOAD: PCA9685 initialized successfully")
        return True
        
    except OSError as e:
        if e.errno == 121:
            queue_message(f"ERROR: I2C Remote I/O error - Check connections and power!")
        else:
            queue_message(f"ERROR: I2C error {e.errno}: {e}")
        return False
        
    except Exception as e:
        queue_message(f"ERROR: Failed to initialize PCA9685: {e}")
        return False

controls = config.get('CONTROLS', {})
_movement_enabled = controls.get('enabled', False) or controls.get('voicemovement', False)

if _movement_enabled:
    if not initialize_pca9685():
        queue_message("WARNING: PCA9685 initialization failed - check hardware")
else:
    pca = None

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
    global leftMainMin, leftMainMax, leftForarmMin, leftForarmMax, leftHandMin, leftHandMax
    global rightMainMin, rightMainMax, rightForarmMin, rightForarmMax, rightHandMin, rightHandMax
    global leftMainOffset, leftForearmOffset, leftHandOffset
    global rightMainOffset, rightForearmOffset, rightHandOffset
    global perfectLeftHeightOffset, leftUpHeight, leftNeutralHeight, leftDownHeight
    global perfectRightHeightOffset, rightUpHeight, rightNeutralHeight, rightDownHeight
    global perfectLeftLegOffset, forwardLeftLeg, neutralLeftLeg, backLeftLeg
    global perfectRightLegOffset, forwardRightLeg, neutralRightLeg, backRightLeg
    global ARMS_PRESENT

    cfg = load_config()
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

def set_servo_pwm(channel, pwm_value):
    global _channels_initialized

    if pca is None:
        return False
    
    duty_cycle = pulse_to_duty_cycle(pwm_value)

    for attempt in range(MAX_RETRIES):
        try:
            pca.channels[channel].duty_cycle = duty_cycle
            _channels_initialized.add(channel)
            return True
            
        except OSError as e:
            if e.errno == 121:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(0.05)
                    continue
                else:
                    queue_message(f"I2C error on channel {channel} after {MAX_RETRIES} attempts")
            return False
            
        except Exception as e:
            queue_message(f"Error setting PWM on channel {channel}: {e}")
            return False
    
    return False

def initialize_servos():
    if pca is None:
        controls = config.get('CONTROLS', {})
        if controls.get('enabled', False) or controls.get('voicemovement', False):
            queue_message("WARNING: Cannot initialize servos - PCA9685 not available")
        return

    try:
        for channel in range(16):
            pca.channels[channel].duty_cycle = 0
    except Exception as e:
        queue_message(f"Error initializing servos: {e}")

    time.sleep(0.1)

    # Gently re-engage servos at their saved positions before moving to neutral
    if servo_positions:
        for channel, value in servo_positions.items():
            set_servo_pwm(int(channel), value)
            time.sleep(0.02)
        time.sleep(0.3)

    reset_positions()
    print("All servos initialized")

def disable_all_servos():
    global _channels_initialized

    if pca is None:
        _channels_initialized.clear()
        return
    
    try:
        for channel in range(16):
            pca.channels[channel].duty_cycle = 0
    except Exception as e:
        queue_message(f"Error disabling servos: {e}")

    _channels_initialized.clear()
    
    time.sleep(0.05)

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
    time.sleep(0.2)
    move_legs(50, 50, 50, 50, 0.5)
    time.sleep(0.3)

    move_arm(1, 1, 1, 1, 1, 1, 0.3)
    time.sleep(0.5)

    disable_all_servos()

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

def cleanup():
    
    disable_all_servos()

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
    get_names_by_type
)

if __name__ == "__main__":
    initialize_servos()
