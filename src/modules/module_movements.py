"""
Module: Movements
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
import time
import modules.module_servoctl as servoctl

move_legs = servoctl.move_legs
move_legs_timed = servoctl.move_legs_timed
move_arm = servoctl.move_arm
disable_all_servos = servoctl.disable_all_servos
HOLD = servoctl.HOLD

_swap_directions = False

def set_swap_turn_directions(swap: bool):
    """Set whether to swap left/right turn directions"""
    global _swap_directions
    _swap_directions = swap

def get_swap_turn_directions() -> bool:
    """Get current direction swap setting"""
    return _swap_directions


def _body_swing_profile(direction, fast=False):
    """Return the paired-leg body-swing gait used by the original chassis."""
    # A lower height percentage raises the chassis. Each vertical and horizontal
    # action is a separate keyframe: raise, swing, lower, lift, then leg return.
    # This matches the stable manual gait and avoids moving the center of mass
    # diagonally through the body's forward pivot. Keep the stride conservative
    # so the feet do not drag as the legs catch up.
    if servoctl.ARMS_PRESENT:
        stride = 30
        raised_height, planted_height, unloaded_height = 32, 78, 16
    else:
        stride = 26
        raised_height, planted_height, unloaded_height = 38, 72, 22

    stride_target = 50 - stride if direction == "forward" else 50 + stride
    if fast:
        timings = (0.22, 0.35, 0.36, 0.38, 0.48, 0.30, 0.26)
    else:
        timings = (0.30, 0.50, 0.48, 0.54, 0.66, 0.40, 0.34)
    return stride_target, raised_height, planted_height, unloaded_height, timings


def _run_body_swing(direction, cycles, fast=False):
    """Swing the chassis first, then bring both legs underneath it."""
    if servoctl.MOVING:
        return

    servoctl.MOVING = True
    servoctl._notify_movement_start()
    try:
        profile = _body_swing_profile(direction, fast=fast)
        stride_target, raised_height, planted_height, unloaded_height, timings = profile
        (
            raise_time, swing_time, lower_time, unload_time,
            follow_time, replant_time, neutral_time,
        ) = timings

        move_legs_timed(50, 50, 50, 50, duration=0.25 if fast else 0.36)

        for _ in range(cycles):
            # 1. Raise the chassis fully without changing horizontal position.
            # 2. Swing the raised chassis horizontally without changing height.
            # 3. Lower the chassis vertically at the completed swing position,
            # then let it settle securely before lifting the legs.
            move_legs_timed(raised_height, raised_height, 50, 50, duration=raise_time)
            move_legs_timed(
                raised_height, raised_height, stride_target, stride_target,
                duration=swing_time,
            )
            move_legs_timed(
                planted_height, planted_height, stride_target, stride_target,
                duration=lower_time,
            )
            servoctl.wait_for_movement(0.12 if fast else 0.16)

            # 4. Lift both feet completely clear while preserving the chassis
            # position. Pause briefly at full clearance before moving them.
            # 5. Bring both legs back underneath the body with minimal drag.
            move_legs_timed(
                unloaded_height, unloaded_height, stride_target, stride_target,
                duration=unload_time,
            )
            servoctl.wait_for_movement(0.10 if fast else 0.14)
            move_legs_timed(
                unloaded_height, unloaded_height, 50, 50,
                duration=follow_time,
            )

            # 6. Replant the feet, then return to a balanced neutral height.
            move_legs_timed(
                raised_height, raised_height, 50, 50,
                duration=replant_time,
            )
            move_legs_timed(50, 50, 50, 50, duration=neutral_time)

        servoctl.wait_for_movement(0.12)
        disable_all_servos()
    finally:
        servoctl.MOVING = False
        servoctl._notify_movement_end()


def step_forward():
    """One quick body-first forward swing followed by both legs."""
    _run_body_swing("forward", cycles=1, fast=True)


def walk_forward():
    """Two full body-first forward swings for greater travel."""
    _run_body_swing("forward", cycles=2, fast=False)


def step_backward():
    """One quick body-first backward swing followed by both legs."""
    _run_body_swing("backward", cycles=1, fast=True)


def walk_backward():
    """Two full body-first backward swings for greater travel."""
    _run_body_swing("backward", cycles=2, fast=False)


def _turn_right_impl():
    """Internal implementation of turn right"""
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(70, 70, 50, 50, 0.9)
            move_legs(70, 70, 65, 35, 0.9)
            move_legs(45, 45, 65, 35, 0.9)
            move_legs(52, 52, 50, 50, 0.8)
            move_legs(50, 50, 50, 50, 0.8)
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def _turn_right_slow_impl():
    """Internal implementation of turn right slow"""
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(40, 70, 50, 50, 0.7)
            move_legs(40, 70, 40, 50, 0.7)
            move_legs(70, 50, 40, 50, 0.7)
            move_legs(70, 50, 50, 50, 0.7)
            move_legs(50, 50, 50, 50, 0.9)
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def _turn_left_impl():
    """Internal implementation of turn left"""
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(70, 70, 50, 50, 0.9)
            move_legs(70, 70, 35, 65, 0.9)
            move_legs(45, 45, 35, 65, 0.9)
            move_legs(52, 52, 50, 50, 0.8)
            move_legs(50, 50, 50, 50, 0.8)
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def _turn_left_slow_impl():
    """Internal implementation of turn left slow"""
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(70, 40, 50, 50, 0.7)
            move_legs(70, 40, 50, 40, 0.7)
            move_legs(50, 70, 50, 40, 0.7)
            move_legs(50, 70, 50, 50, 0.7)
            move_legs(50, 50, 50, 50, 0.9)
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def turn_right():
    """Turn right (or left if swap_turn_directions is enabled)"""
    if _swap_directions:
        _turn_left_impl()
    else:
        _turn_right_impl()


def turn_right_slow():
    """Turn right slowly (or left if swap_turn_directions is enabled)"""
    if _swap_directions:
        _turn_left_slow_impl()
    else:
        _turn_right_slow_impl()


def turn_left():
    """Turn left (or right if swap_turn_directions is enabled)"""
    if _swap_directions:
        _turn_right_impl()
    else:
        _turn_left_impl()


def turn_left_slow():
    """Turn left slowly (or right if swap_turn_directions is enabled)"""
    if _swap_directions:
        _turn_right_slow_impl()
    else:
        _turn_left_slow_impl()


def right_hi():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(None, 50, None, 50, 0.8)
            move_legs(None, 80, None, 50, 0.8)
            move_legs(None, 80, None, 80, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 50, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 50, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 50, 1, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.8)
            move_legs(None, 50, None, 50, 0.8)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_hi():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, None, 50, None, 0.8)
            move_legs(80, None, 50, None, 0.8)
            move_legs(80, None, 80, None, 0.8)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 50, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 50, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 50, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.8)
            move_legs(50, None, 50, None, 0.8)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def laugh():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            for _ in range(5):
                move_legs(50, 50, 50, 50, 1)
                time.sleep(0.1)
                move_legs(1, 1, 50, 50, 1)
                time.sleep(0.1)
            move_legs(50, 50, 50, 50, 1)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()

def excited():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            for _ in range(4):
                move_legs(40, 60, 45, 50, 0.95) 
                move_legs(60, 40, 50, 45, 0.95)
            move_legs(50, 50, 50, 50, 0.9)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def swing_legs():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 1)
            time.sleep(0.1)
            move_legs(100, 100, 50, 50, 1)
            time.sleep(0.1)
            for _ in range(3):
                move_legs(0, 0, 20, 80, 0.6)
                time.sleep(0.1)
                move_legs(0, 0, 80, 20, 0.6)
                time.sleep(0.1)
            move_legs(0, 0, 50, 50, 0.6)
            time.sleep(0.1)
            move_legs(50, 50, 50, 50, 0.7)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_pezz_dispenser():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.4)            
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(98, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 100, None, None, None, 0.9)
            time.sleep(5)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_pezz_dispenser():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)            
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 100, 0.9)
            time.sleep(5)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.8)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def monster():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.4)
            move_legs(80, 80, 50, 50, 0.5)
            move_legs(80, 80, 65, 65, 0.5)
            time.sleep(0.2)
            move_arm(1, 1, 1, 1, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(100, 1, 1, 100, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 100, 1, HOLD, 100, 1, 1)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, HOLD, HOLD, 100, 1)
            time.sleep(0.2)
            move_arm(HOLD, 100, 100, HOLD, 50, 50, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 50, 50, HOLD, 100, 100, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 100, 100, HOLD, 50, 50, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 50, 50, HOLD, 100, 100, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 100, 100, HOLD, 100, 100, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, HOLD, HOLD, 100, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, HOLD, HOLD, 1, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, HOLD, HOLD, 100, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, HOLD, HOLD, 1, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, HOLD, HOLD, 100, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, HOLD, HOLD, 1, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 1, HOLD, HOLD, 1, HOLD, 0.8)
            time.sleep(0.2)
            move_arm(1, HOLD, HOLD, 1, HOLD, HOLD, 0.8)
            time.sleep(0.2)
            move_legs(80, 80, 50, 50, 0.5)
            move_legs(50, 50, 50, 50, 0.4)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def pose():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.6)
            move_legs(30, 30, 40, 40, 0.6)
            move_legs(80, 80, 30, 30, 0.6)
            time.sleep(3)
            move_legs(80, 80, 30, 30, 0.8)
            move_legs(30, 30, 30, 30, 0.8)
            move_legs(30, 30, 40, 40, 0.6)
            move_legs(50, 50, 50, 50, 0.6)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def bow():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.4)
            move_legs(15, 15, 50, 50, 0.7)
            move_legs(15, 15, 70, 70, 0.7)
            move_legs(60, 60, 70, 70, 0.7)
            move_legs(95, 95, 65, 65, 0.7)
            time.sleep(3)
            move_legs(15, 15, 65, 65, 0.7)
            move_legs(50, 50, 50, 50, 0.4)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def tilt_right():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(20, 80, 50, 50, 0.9)
            time.sleep(3)
            move_legs(50, 50, 50, 50, 0.9)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def tilt_left():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(80, 20, 50, 50, 0.9)
            time.sleep(3)
            move_legs(50, 50, 50, 50, 0.9)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def side_side():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(10, 90, 50, 50, 0.9)
            move_legs(90, 10, 50, 50, 0.9)
            move_legs(10, 90, 50, 50, 0.9)
            move_legs(90, 10, 50, 50, 0.9)
            move_legs(10, 90, 50, 50, 0.9)
            move_legs(90, 10, 50, 50, 0.9)
            move_legs(50, 50, 50, 50, 0.9)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def wave_right():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(50, 90, 50, 50, 0.9)
            move_legs(20, 90, 50, 100, 0.9)
            move_legs(20, 90, 50, 70, 0.9)
            move_legs(20, 90, 50, 100, 0.9)
            move_legs(20, 90, 50, 70, 0.9)
            move_legs(50, 90, 50, 100, 0.9)
            move_legs(50, 90, 50, 70, 0.9)
            move_legs(50, 90, 50, 100, 0.9)
            move_legs(50, 90, 50, 70, 0.9)
            move_legs(20, 90, 50, 100, 0.9)
            move_legs(20, 90, 50, 70, 0.9)
            move_legs(20, 90, 50, 100, 0.9)
            move_legs(20, 90, 50, 70, 0.9)
            move_legs(50, 50, 50, 50, 0.8)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def wave_left():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(90, 50, 50, 50, 0.9)
            move_legs(90, 20, 100, 50, 0.9)
            move_legs(90, 20, 70, 50, 0.9)
            move_legs(90, 20, 100, 50, 0.9)
            move_legs(90, 20, 70, 50, 0.9)
            move_legs(90, 50, 100, 50, 0.9)
            move_legs(90, 50, 70, 50, 0.9)
            move_legs(90, 50, 100, 50, 0.9)
            move_legs(90, 50, 70, 50, 0.9)
            move_legs(90, 20, 100, 50, 0.9)
            move_legs(90, 20, 70, 50, 0.9)
            move_legs(90, 20, 100, 50, 0.9)
            move_legs(90, 20, 70, 50, 0.9)
            move_legs(50, 50, 50, 50, 0.8)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def neutral_legs():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(90, 90, None, None, 0.8)
            move_legs(90, 90, 50, 50, 0.8)
            move_legs(50, 50, 50, 50, 0.8)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_point():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.7)
            time.sleep(0.5)
            move_arm(100, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.5)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_point():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.7)
            time.sleep(0.5)
            move_arm(None, None, None, 100, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.5)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_poke():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 100, 1, None, None, None, 0.7)
            time.sleep(0.15)
            move_arm(HOLD, 70, 1, None, None, None, 0.6)
            time.sleep(0.15)
            move_arm(HOLD, 100, 1, None, None, None, 0.6)
            time.sleep(0.15)
            move_arm(HOLD, 70, 1, None, None, None, 0.6)
            time.sleep(0.15)
            move_arm(HOLD, 100, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(1, HOLD, HOLD, None, None, None, 0.5)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_poke():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, 1, 0.7)
            time.sleep(0.15)
            move_arm(None, None, None, HOLD, 70, 1, 0.6)
            time.sleep(0.15)
            move_arm(None, None, None, HOLD, 100, 1, 0.6)
            time.sleep(0.15)
            move_arm(None, None, None, HOLD, 70, 1, 0.6)
            time.sleep(0.15)
            move_arm(None, None, None, HOLD, 100, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 1, HOLD, HOLD, 0.5)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_wave_open():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 100, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 70, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, 100, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, 70, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, 100, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 1, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(1, HOLD, HOLD, None, None, None, 0.5)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_wave_open():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, HOLD, 100, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 70, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 70, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, HOLD, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 1, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 1, HOLD, HOLD, 0.5)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_shy_wave():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 100, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(92, 50, 40, None, None, None, 0.6)
            move_legs(70, 90, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 100, None, None, None, 0.6)
            move_legs(90, 70, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(92, 50, 40, None, None, None, 0.6)
            move_legs(70, 90, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 100, None, None, None, 0.6)
            move_legs(90, 70, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(92, 50, 40, None, None, None, 0.6)
            move_legs(70, 90, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 100, None, None, None, 0.6)
            move_legs(80, 50, 80, 50, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 1, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(1, HOLD, HOLD, None, None, None, 0.5)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_shy_wave():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, HOLD, 100, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, 92, 50, 40, 0.6)
            move_legs(90, 70, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 100, 0.6)
            move_legs(70, 90, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 92, 50, 40, 0.6)
            move_legs(90, 70, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 100, 0.6)
            move_legs(70, 90, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 92, 50, 40, 0.6)
            move_legs(90, 70, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 100, 0.6)
            move_legs(50, 80, 50, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, HOLD, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 1, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 1, HOLD, HOLD, 0.5)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def happy_dance():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, None, 45, 55, 0.9)
            time.sleep(0.1)
            move_legs(None, None, 55, 45, 0.9)
            time.sleep(0.1)
            move_legs(None, None, 45, 55, 0.9)
            time.sleep(0.1)
            move_legs(None, None, 50, 50, 0.9)
            move_legs(20, 80, None, None, 0.9)
            time.sleep(0.1)
            move_legs(80, 20, None, None, 0.9)
            time.sleep(0.1)
            move_legs(20, 80, None, None, 0.9)
            time.sleep(0.1)
            move_legs(50, 50, None, None, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            move_arm(None, HOLD, None, 85, HOLD, None, 0.8)
            time.sleep(0.2)
            move_legs(40, 70, None, None, 0.95)
            time.sleep(0.1)
            move_legs(60, 80, None, None, 0.95)
            time.sleep(0.1)
            move_legs(40, 70, None, None, 0.95)
            time.sleep(0.1)
            move_arm(None, HOLD, None, 1, HOLD, None, 0.8)
            move_legs(80, None, 80, None, 0.9)
            move_arm(85, HOLD, None, None, HOLD, None, 0.8)
            time.sleep(0.15)
            move_legs(80, 80, 70, 70, 0.9)
            move_arm(85, HOLD, None, 85, HOLD, None, 0.7)
            time.sleep(0.25)
            move_legs(20, 90, None, None, 0.9)
            time.sleep(0.12)
            move_legs(90, 20, None, None, 0.9)
            time.sleep(0.12)
            move_legs(20, 90, None, None, 0.9)
            time.sleep(0.12)
            move_legs(80, 80, None, None, 0.9)
            move_arm(1, HOLD, None, 1, HOLD, None, 0.7)
            move_legs(None, None, 50, 50, 0.9)
            time.sleep(0.1)
            move_legs(50, 50, None, None, 0.8)
            time.sleep(0.1)
            move_legs(30, 30, None, None, 0.95)
            time.sleep(0.08)
            move_legs(65, 65, None, None, 0.95)
            time.sleep(0.08)
            move_legs(30, 30, None, None, 0.95)
            time.sleep(0.08)
            move_legs(50, 50, None, None, 0.9)
            time.sleep(0.1)
            move_legs(None, 80, None, 80, 0.95)
            move_arm(None, HOLD, None, 85, HOLD, None, 0.9)
            time.sleep(0.1)
            move_arm(None, HOLD, None, 1, HOLD, None, 0.9)
            move_legs(80, None, 80, None, 0.95)
            move_arm(85, HOLD, None, None, HOLD, None, 0.9)
            time.sleep(0.1)
            move_arm(1, HOLD, None, None, HOLD, None, 0.9)
            move_legs(None, 80, None, 80, 0.95)
            move_arm(None, HOLD, None, 85, HOLD, None, 0.9)
            time.sleep(0.1)
            time.sleep(0.3)
            move_arm(None, HOLD, None, 1, HOLD, None, 0.7)
            move_legs(None, None, 50, 50, 0.9)
            move_legs(50, 50, None, None, 0.8)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def ventilate_on():
    """
    Position tars for better airflow
    """
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._is_ventilate_operation = True
        
        servoctl._notify_movement_start()
        try:
            from modules.module_cputemp import set_ventilating
            
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(25, 25, 50, 50, 0.75)
            move_legs(25, 25, 42, 42, 0.75)
            move_legs(55, 55, 30, 30, 0.75)

            set_ventilating(True)
            
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl._is_ventilate_operation = False
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def ventilate_off():
    from modules.module_cputemp import is_ventilating, set_ventilating
    
    if is_ventilating():
        was_moving = servoctl.MOVING

        servoctl.MOVING = True
        servoctl._is_ventilate_operation = True
        
        if not was_moving:
            servoctl._notify_movement_start()
        
        try:
            move_legs(55, 55, 30, 30, 0.75)
            move_legs(25, 25, 30, 30, 0.75)
            move_legs(25, 25, 50, 50, 0.75)
            move_legs(50, 50, 50, 50, 0.75)
            
            set_ventilating(False)
            
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl._is_ventilate_operation = False
            servoctl.MOVING = was_moving
            if not was_moving:
                servoctl._notify_movement_end()


# All user-facing presets share one non-blocking command lock. This prevents
# controller, voice, and UI threads from entering two pose scripts at once.
_SERIALIZED_MOVEMENTS = (
    "step_forward", "walk_forward", "step_backward", "walk_backward",
    "turn_right", "turn_right_slow", "turn_left", "turn_left_slow",
    "right_hi", "left_hi", "laugh", "excited", "swing_legs",
    "left_pezz_dispenser", "right_pezz_dispenser", "monster", "pose",
    "bow", "tilt_right", "tilt_left", "side_side", "wave_right",
    "wave_left", "neutral_legs", "left_point", "right_point",
    "left_poke", "right_poke", "left_wave_open", "right_wave_open",
    "left_shy_wave", "right_shy_wave", "happy_dance",
)

for _movement_name in _SERIALIZED_MOVEMENTS:
    if _movement_name in globals():
        globals()[_movement_name] = servoctl.movement_command(globals()[_movement_name])
