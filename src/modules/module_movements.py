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


def _gait_profile(fast=False):
    """Return conservative gait geometry and timing for this chassis."""
    # Arms raise the centre of mass, so use a little more weight transfer but
    # avoid the old 95% height extremes that made the robot lunge.
    weight_shift = 18 if servoctl.ARMS_PRESENT else 15
    stride = 21 if servoctl.ARMS_PRESENT else 18
    if fast:
        return weight_shift, stride, (0.18, 0.22, 0.16)
    return weight_shift, stride, (0.30, 0.34, 0.24)


def _run_walk(direction, cycles, fast=False):
    """Run a balanced six-phase walking gait in either direction."""
    if servoctl.MOVING:
        return

    servoctl.MOVING = True
    servoctl._notify_movement_start()
    try:
        shift, stride, timings = _gait_profile(fast=fast)
        transfer_time, swing_time, plant_time = timings
        stride_target = 50 - stride if direction == "forward" else 50 + stride
        left_up, left_down = 50 - shift, 50 + shift
        right_up, right_down = 50 - shift, 50 + shift

        move_legs_timed(50, 50, 50, 50, duration=0.24 if fast else 0.34)

        for _ in range(cycles):
            # Load the right side, advance the unloaded left foot, then plant.
            move_legs_timed(left_up, right_down, 50, 50, duration=transfer_time)
            move_legs_timed(left_up, right_down, stride_target, 50, duration=swing_time)
            move_legs_timed(50, 50, stride_target, 50, duration=plant_time)

            # Transfer onto the left side while the chassis advances, then
            # swing and plant the right foot.
            move_legs_timed(left_down, right_up, 50, 50, duration=transfer_time)
            move_legs_timed(left_down, right_up, 50, stride_target, duration=swing_time)
            move_legs_timed(50, 50, 50, stride_target, duration=plant_time)

        # Unload the final advanced foot before bringing it home. This avoids
        # dragging it across the floor from a fully weighted neutral stance.
        move_legs_timed(left_down, right_up, 50, stride_target, duration=transfer_time)
        move_legs_timed(left_down, right_up, 50, 50, duration=swing_time)
        move_legs_timed(50, 50, 50, 50, duration=plant_time)
        servoctl.wait_for_movement(0.12)
        disable_all_servos()
    finally:
        servoctl.MOVING = False
        servoctl._notify_movement_end()


def step_forward():
    """One quick, controlled forward gait cycle."""
    _run_walk("forward", cycles=1, fast=True)


def walk_forward():
    """Two stable forward gait cycles."""
    _run_walk("forward", cycles=2, fast=False)


def step_backward():
    """One quick, controlled backward gait cycle."""
    _run_walk("backward", cycles=1, fast=True)


def walk_backward():
    """Two stable backward gait cycles."""
    _run_walk("backward", cycles=2, fast=False)


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
