"""Pure calibration model used by the PySide6 servo tester.

This module contains no Qt or hardware imports.  It owns servo metadata,
calibration-range arithmetic, and config text updates so those rules can be
tested without creating a GUI or touching I2C.
"""

from __future__ import annotations

import configparser
from copy import deepcopy
from pathlib import Path


SERVO_DEFINITIONS = {
    "left_height": {
        "label": "LEFT HEIGHT", "config": "perfectLeftHeightOffset", "channel": 0,
        "preview_base": 350, "preview_sign": 1,
        "limits": ("leftUpHeight", "leftDownHeight"),
    },
    "left_leg": {
        "label": "LEFT LEG  (FORWARD / BACK)", "config": "perfectLeftLegOffset", "channel": 2,
        "preview_base": 300, "preview_sign": 1,
        "limits": ("forwardLeftLeg", "backLeftLeg"),
    },
    "left_main": {
        "label": "LEFT MAIN ARM", "config": "leftMainOffset", "channel": 4,
        "preview_key": "leftMainMin", "limits": ("leftMainMin", "leftMainMax"),
    },
    "left_forearm": {
        "label": "LEFT FOREARM", "config": "leftForearmOffset", "channel": 5,
        "preview_key": "leftForarmMin", "limits": ("leftForarmMin", "leftForarmMax"),
    },
    "left_hand": {
        "label": "LEFT HAND", "config": "leftHandOffset", "channel": 6,
        "preview_key": "leftHandMin", "limits": ("leftHandMin", "leftHandMax"),
    },
    "right_height": {
        "label": "RIGHT HEIGHT", "config": "perfectRightHeightOffset", "channel": 1,
        "preview_base": 350, "preview_sign": -1, "limit_sign": -1,
        "limits": ("rightUpHeight", "rightDownHeight"),
    },
    "right_leg": {
        "label": "RIGHT LEG  (FORWARD / BACK)", "config": "perfectRightLegOffset", "channel": 3,
        "preview_base": 300, "preview_sign": 1,
        "limits": ("forwardRightLeg", "backRightLeg"),
    },
    "right_main": {
        "label": "RIGHT MAIN ARM", "config": "rightMainOffset", "channel": 7,
        "preview_key": "rightMainMin", "limits": ("rightMainMin", "rightMainMax"),
    },
    "right_forearm": {
        "label": "RIGHT FOREARM", "config": "rightForearmOffset", "channel": 8,
        "preview_key": "rightForarmMin", "limits": ("rightForarmMin", "rightForarmMax"),
    },
    "right_hand": {
        "label": "RIGHT HAND", "config": "rightHandOffset", "channel": 9,
        "preview_key": "rightHandMin", "limits": ("rightHandMin", "rightHandMax"),
    },
}

MOVEMENT_CATEGORIES = ("Locomotion", "Body", "Arms", "All")
LOCOMOTION_MOVEMENTS = {
    "step_forward", "walk_forward", "step_backward", "walk_backward",
    "turn_left", "turn_left_slow", "turn_right", "turn_right_slow",
    "neutral_legs",
}
BODY_MOVEMENTS = {
    "pose", "bow", "tilt_right", "tilt_left", "side_side",
    "wave_right", "wave_left", "excited", "laugh", "swing_legs",
}


def read_servo_config(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return dict(parser.items("SERVO")) if parser.has_section("SERVO") else {}


class ServoCalibrationModel:
    """Mutable calibration state with bounded endpoint calculations."""

    def __init__(self, servo_config: dict[str, str]):
        self.config = dict(servo_config)
        self.servos = self._build_servos()
        self.saved_servos = deepcopy(self.servos)

    def config_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def offset_bounds(self, servo_id: str) -> tuple[int, int]:
        definition = SERVO_DEFINITIONS[servo_id]
        is_arm = "_height" not in servo_id and "_leg" not in servo_id
        lower, upper = (-90, 90) if is_arm else (-50, 50)
        sign = int(definition.get("limit_sign", 1))
        for key in definition["limits"]:
            base = self.config_int(key, 300)
            if sign > 0:
                lower = max(lower, 10 - base)
                upper = min(upper, 600 - base)
            else:
                lower = max(lower, base - 600)
                upper = min(upper, base - 10)
        return (0, 0) if lower > upper else (int(lower), int(upper))

    def effective_endpoints(self, servo_id: str) -> tuple[int, int]:
        definition = SERVO_DEFINITIONS[servo_id]
        offset = int(self.servos.get(servo_id, {}).get("value", 0))
        sign = int(definition.get("limit_sign", 1))
        first, second = definition["limits"]
        return (
            self.config_int(first, 300) + sign * offset,
            self.config_int(second, 300) + sign * offset,
        )

    def range_target_pulse(self, servo_id: str, percent: int) -> int:
        start, end = self.effective_endpoints(servo_id)
        normalized = max(0, min(100, int(percent))) / 100.0
        return round(start + (end - start) * normalized)

    def target_pulse(self, servo_id: str, offset: int) -> int:
        definition = SERVO_DEFINITIONS[servo_id]
        base = definition.get("preview_base")
        if base is None:
            base = self.config_int(definition["preview_key"], 300)
        return int(base) + int(definition.get("preview_sign", 1)) * int(offset)

    def offset_is_safe(self, servo_id: str, offset: int) -> bool:
        minimum, maximum = self.offset_bounds(servo_id)
        return minimum <= int(offset) <= maximum

    def arms_present(self) -> bool:
        return str(self.config.get("arms_present", "false")).lower() in {
            "1", "true", "yes", "on",
        }

    def offset_values(self) -> dict[str, int]:
        return {
            SERVO_DEFINITIONS[servo_id]["config"]: int(servo["value"])
            for servo_id, servo in self.servos.items()
        }

    def update_config_text(self, text: str) -> str:
        lines = text.splitlines(keepends=True)
        values = self.offset_values()
        in_servo = False
        updated: set[str] = set()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.lower() == "[servo]":
                in_servo = True
                continue
            if in_servo and stripped.startswith("["):
                in_servo = False
            if not in_servo or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key not in values:
                continue
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            comment = ""
            if "#" in line:
                comment = "  #" + line.split("#", 1)[1].rstrip("\r\n")
            lines[index] = f"{key} = {values[key]}{comment}{newline}"
            updated.add(key)
        missing = [key for key in values if key not in updated]
        if missing:
            raise KeyError("Missing [SERVO] settings: " + ", ".join(missing))
        return "".join(lines)

    def accept_saved(self) -> None:
        self.saved_servos = deepcopy(self.servos)

    def revert(self) -> None:
        self.servos = deepcopy(self.saved_servos)

    def reload_config(self, config: dict[str, str]) -> None:
        self.config = dict(config)

    def _build_servos(self) -> dict[str, dict]:
        servos = {}
        for servo_id, definition in SERVO_DEFINITIONS.items():
            raw = self.config.get(definition["config"], "0")
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = 0
            minimum, maximum = self.offset_bounds(servo_id)
            value = max(minimum, min(maximum, value))
            servos[servo_id] = {
                "id": servo_id,
                "label": definition["label"],
                "value": value,
                "minimum": minimum,
                "maximum": maximum,
                "unit": "ticks",
            }
        return servos
