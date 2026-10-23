"""PySide6/QML servo calibration UI for TARS.

On a Raspberry Pi this app uses the project's existing PCA9685 servo module.
On other computers it automatically uses a safe mock backend. Pass ``--mock``
on the Pi to explore the interface without moving hardware.
"""

from __future__ import annotations

import argparse
import configparser
import os
import shutil
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path

from modules.module_gait import body_swing_diagnostic_phases


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TARS servo calibration QML app")
    parser.add_argument("--fullscreen", action="store_true", help="open full screen")
    parser.add_argument("--diagnostic", action="store_true", help="open the gait diagnostic tab")
    parser.add_argument("--screenshot", type=Path, help="save a screenshot and exit")
    parser.add_argument("--window-size", metavar="WIDTHxHEIGHT", help=argparse.SUPPRESS)
    backend = parser.add_mutually_exclusive_group()
    backend.add_argument("--mock", action="store_true", help="never access servo hardware")
    backend.add_argument("--hardware", action="store_true", help="force PCA9685 hardware mode")
    return parser.parse_args()


ARGS = _parse_args()

if ARGS.screenshot and "QT_QPA_PLATFORM" not in os.environ:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

import shiboken6
from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent

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


def _is_raspberry_pi() -> bool:
    try:
        return "raspberry pi" in Path("/proc/device-tree/model").read_text().lower()
    except (OSError, UnicodeDecodeError):
        return False


def _find_config_path() -> Path | None:
    for path in (ROOT / "config.ini", PROJECT_ROOT / "config.ini"):
        if path.is_file():
            return path
    return None


def _read_servo_config(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return dict(parser.items("SERVO")) if parser.has_section("SERVO") else {}


def _servo(servo_id: str, value: int, minimum: int, maximum: int) -> dict:
    definition = SERVO_DEFINITIONS[servo_id]
    return {
        "id": servo_id,
        "label": definition["label"],
        "value": value,
        "minimum": minimum,
        "maximum": maximum,
        "unit": "ticks",
    }


class ServoCalibrationController(QObject):
    """State and bounded hardware operations exposed to QML."""

    servosChanged = Signal()
    stateChanged = Signal()
    statusChanged = Signal()
    profileChanged = Signal()
    movementsChanged = Signal()
    diagnosticsChanged = Signal()
    rangeTestChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._config_path = _find_config_path()
        self._servo_config = _read_servo_config(self._config_path)
        self._servoctl = None
        self._io_lock = threading.RLock()
        self._preview_condition = threading.Condition()
        self._preview_request: dict | None = None
        self._preview_stop = False
        self._preview_cancel = threading.Event()
        self._preview_thread: threading.Thread | None = None
        self._preview_interval = 0.04
        self._preview_step_ticks = 6
        # Keep strong references to the standalone tester's I2C/PCA objects.
        # The working legacy tester owns this hardware session directly, so the
        # QML tester does the same instead of relying on module import state.
        self._i2c = None
        self._pca = None
        self._hardware_connected = False
        self._hardware_error = ""
        self._movement_active = False
        self._movement_category = "Locomotion"
        self._diagnostic_direction = "forward"
        self._diagnostic_phase = -1
        self._range_servo_id = "left_height"
        self._range_percent = 50
        self._range_applied_percent = 50
        self._range_armed = False
        self._range_busy = False
        self._power_transition = False

        self._servos = {}
        for servo_id, definition in SERVO_DEFINITIONS.items():
            raw = self._servo_config.get(definition["config"], "0")
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = 0
            minimum, maximum = self._offset_bounds(servo_id)
            value = max(minimum, min(maximum, value))
            self._servos[servo_id] = _servo(servo_id, value, minimum, maximum)

        self._saved_servos = deepcopy(self._servos)
        self._dirty = False
        self._servo_power = True
        self._profile = "Default"
        self._battery = 81
        self._voltage = 11.74

        wants_hardware = ARGS.hardware or (not ARGS.mock and _is_raspberry_pi())
        if wants_hardware:
            self._connect_hardware()

        if self._hardware_connected:
            # Connecting over I2C does not imply that PWM outputs are active.
            # Start explicitly disabled so POWER ON always performs real writes.
            self._servo_power = False
            self._status = "PCA9685 online · support TARS, then press POWER ON"
        elif wants_hardware:
            self._status = f"Hardware unavailable · {self._hardware_error}"
            self._servo_power = False
        else:
            self._status = "Mock mode · use --hardware to force PCA9685 control"

        self._preview_thread = threading.Thread(
            target=self._preview_worker,
            name="servo-preview",
            daemon=True,
        )
        self._preview_thread.start()

    def _connect_hardware(self) -> None:
        with self._io_lock:
            candidate_i2c = None
            candidate_pca = None
            try:
                import board
                import busio
                from adafruit_pca9685 import PCA9685

                import modules.module_servoctl as servoctl

                # The standalone tester owns both objects. Mirroring both into
                # module_servoctl lets its recovery and cleanup paths close the
                # complete hardware session rather than only the PCA object.
                candidate_i2c = busio.I2C(board.SCL, board.SDA)
                candidate_pca = PCA9685(candidate_i2c, address=0x40)
                candidate_pca.frequency = 50
                candidate_pca.channels[15].duty_cycle = 0

                self._i2c = candidate_i2c
                self._pca = candidate_pca
                servoctl._i2c = candidate_i2c
                servoctl.pca = candidate_pca
                servoctl._channels_initialized.clear()
                self._servoctl = servoctl
                self._hardware_connected = True
                self._hardware_error = ""

                # Begin from a known, torque-free state. ENABLE PWM issues
                # fresh writes only after the user has supported the robot.
                servoctl.disable_all_servos()
            except Exception as exc:
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
                self._hardware_error = str(exc)
                self._hardware_connected = False
                self._pca = None
                self._i2c = None
                print(f"[SERVO TESTER] Hardware mode unavailable: {exc}", file=sys.stderr)
        self.stateChanged.emit()

    def _reconnect_hardware(self) -> bool:
        """Reopen a discarded controller, leaving every PWM output off."""
        self._set_status("PCA9685 connection lost · attempting recovery")
        self._connect_hardware()
        if self._hardware_connected:
            # A reconnect disables every channel.  Do not silently energize
            # only the joint whose write failed while the other joints are
            # unsupported; require the operator to re-enable the complete pose.
            self._servo_power = False
            self._range_armed = False
            self._range_busy = False
            self.stateChanged.emit()
            self.rangeTestChanged.emit()
            self._set_status("PCA9685 recovered · PWM remains off; support TARS and enable it again")
            return True
        self._servo_power = False
        self.stateChanged.emit()
        self._set_status(f"PCA9685 recovery failed · {self._hardware_error}")
        return False

    def _side(self, prefix: str) -> list[dict]:
        return [deepcopy(item) for key, item in self._servos.items() if key.startswith(prefix)]

    @Property("QVariantList", notify=servosChanged)
    def leftServos(self) -> list[dict]:
        return self._side("left_")

    @Property("QVariantList", notify=servosChanged)
    def rightServos(self) -> list[dict]:
        return self._side("right_")

    @Property(bool, notify=stateChanged)
    def unsavedChanges(self) -> bool:
        return self._dirty

    @Property(bool, notify=stateChanged)
    def servoPower(self) -> bool:
        return self._servo_power

    @Property(bool, notify=stateChanged)
    def hardwareConnected(self) -> bool:
        return self._hardware_connected

    @Property(str, notify=stateChanged)
    def hardwareModeText(self) -> str:
        if not self._hardware_connected:
            return "MOCK MODE"
        return "CONNECTED · PWM ON" if self._servo_power else "CONNECTED · PWM OFF"

    @Property(str, notify=statusChanged)
    def statusText(self) -> str:
        return self._status

    @Property(str, notify=profileChanged)
    def activeProfile(self) -> str:
        return self._profile

    @Property(int, constant=True)
    def batteryPercent(self) -> int:
        return self._battery

    @Property(float, constant=True)
    def batteryVoltage(self) -> float:
        return self._voltage

    @Property(bool, notify=stateChanged)
    def movementActive(self) -> bool:
        return self._movement_active

    @Property(bool, notify=stateChanged)
    def powerTransition(self) -> bool:
        return self._power_transition

    @Property(bool, notify=rangeTestChanged)
    def rangeTestArmed(self) -> bool:
        return self._range_armed

    @Property(bool, notify=rangeTestChanged)
    def rangeTestBusy(self) -> bool:
        return self._range_busy

    @Property("QVariantList", notify=rangeTestChanged)
    def rangeServoOptions(self) -> list[dict]:
        options = []
        arms_present = self._arms_present()
        for servo_id, definition in SERVO_DEFINITIONS.items():
            is_arm = "_height" not in servo_id and "_leg" not in servo_id
            minimum, maximum = self._effective_endpoints(servo_id)
            options.append({
                "id": servo_id,
                "label": definition["label"],
                "channel": definition["channel"],
                "available": arms_present or not is_arm,
                "minimumPulse": minimum,
                "maximumPulse": maximum,
            })
        return options

    @Property(str, notify=rangeTestChanged)
    def selectedRangeServo(self) -> str:
        return self._range_servo_id

    @Property(str, notify=rangeTestChanged)
    def selectedRangeServoLabel(self) -> str:
        return SERVO_DEFINITIONS[self._range_servo_id]["label"]

    @Property(int, notify=rangeTestChanged)
    def rangeTestPercent(self) -> int:
        return self._range_percent

    @Property(int, notify=rangeTestChanged)
    def rangeTestAppliedPercent(self) -> int:
        return self._range_applied_percent

    @Property(int, notify=rangeTestChanged)
    def rangeTestPulse(self) -> int:
        return self._range_target_pulse(self._range_servo_id, self._range_percent)

    @Property(int, notify=rangeTestChanged)
    def rangeTestMinimumPulse(self) -> int:
        return self._effective_endpoints(self._range_servo_id)[0]

    @Property(int, notify=rangeTestChanged)
    def rangeTestMaximumPulse(self) -> int:
        return self._effective_endpoints(self._range_servo_id)[1]

    @Property("QVariantList", constant=True)
    def movementCategories(self) -> list[str]:
        return list(MOVEMENT_CATEGORIES)

    @Property(str, notify=movementsChanged)
    def movementCategory(self) -> str:
        return self._movement_category

    @Property("QVariantList", notify=movementsChanged)
    def movementPresets(self) -> list[dict]:
        from modules.module_movement_registry import HAS_ARMS, MOVEMENTS

        arms_present = str(self._servo_config.get("arms_present", "false")).lower() in (
            "1", "true", "yes", "on"
        )
        presets = []
        for key, metadata in MOVEMENTS.items():
            if key in LOCOMOTION_MOVEMENTS:
                category = "Locomotion"
            elif key in BODY_MOVEMENTS:
                category = "Body"
            else:
                category = "Arms"
            if self._movement_category != "All" and category != self._movement_category:
                continue
            needs_arms = metadata["type"] == HAS_ARMS
            presets.append({
                "key": key,
                "name": metadata["name"],
                "category": category,
                "needsArms": needs_arms,
                "available": not self._hardware_connected or not needs_arms or arms_present,
            })
        return presets

    @Property(str, notify=diagnosticsChanged)
    def diagnosticDirection(self) -> str:
        return self._diagnostic_direction

    @Property(int, notify=diagnosticsChanged)
    def diagnosticPhase(self) -> int:
        return self._diagnostic_phase

    @Property(str, notify=diagnosticsChanged)
    def diagnosticProfileText(self) -> str:
        return "ORIGINAL ARMS STEP" if self._arms_present() else "ORIGINAL NO-ARMS STEP"

    @Property("QVariantList", notify=diagnosticsChanged)
    def diagnosticPhases(self) -> list[dict]:
        phases = body_swing_diagnostic_phases(
            self._diagnostic_direction,
            self._arms_present(),
        )
        result = []
        for phase in phases:
            item = dict(phase)
            left_height, right_height, left_leg, right_leg = item.pop("pose")
            item["poseText"] = (
                f"H {left_height}/{right_height}  ·  L {left_leg}/{right_leg}"
                f"  ·  SPEED {item['speed']:.1f}"
            )
            item["completed"] = item["index"] <= self._diagnostic_phase
            item["next"] = item["index"] == self._diagnostic_phase + 1
            item["selected"] = item["index"] == self._diagnostic_phase
            result.append(item)
        return result

    @Property(QUrl, constant=True)
    def tarsImageUrl(self) -> QUrl:
        image_path = PROJECT_ROOT / "media" / "2026-02-03 192140.png"
        return QUrl.fromLocalFile(str(image_path))

    def _set_status(self, message: str) -> None:
        self._status = message
        print(f"[SERVO TESTER] {message}", flush=True)
        self.statusChanged.emit()

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty != dirty:
            self._dirty = dirty
            self.stateChanged.emit()

    def _config_int(self, key: str, default: int) -> int:
        try:
            return int(self._servo_config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _offset_bounds(self, servo_id: str) -> tuple[int, int]:
        """Return only offsets that keep every configured endpoint valid."""
        definition = SERVO_DEFINITIONS[servo_id]
        is_arm = "_height" not in servo_id and "_leg" not in servo_id
        lower, upper = (-90, 90) if is_arm else (-50, 50)
        sign = int(definition.get("limit_sign", 1))
        for key in definition["limits"]:
            base = self._config_int(key, 300)
            if sign > 0:
                lower = max(lower, 10 - base)
                upper = min(upper, 600 - base)
            else:
                lower = max(lower, base - 600)
                upper = min(upper, base - 10)
        if lower > upper:
            return 0, 0
        return int(lower), int(upper)

    def _effective_endpoints(self, servo_id: str) -> tuple[int, int]:
        definition = SERVO_DEFINITIONS[servo_id]
        offset = int(self._servos.get(servo_id, {}).get("value", 0))
        sign = int(definition.get("limit_sign", 1))
        first, second = definition["limits"]
        return (
            self._config_int(first, 300) + sign * offset,
            self._config_int(second, 300) + sign * offset,
        )

    def _range_target_pulse(self, servo_id: str, percent: int) -> int:
        start, end = self._effective_endpoints(servo_id)
        normalized = max(0, min(100, int(percent))) / 100.0
        return round(start + (end - start) * normalized)

    def _arms_present(self) -> bool:
        return str(self._servo_config.get("arms_present", "false")).lower() in (
            "1", "true", "yes", "on"
        )

    def _queue_preview_targets(self, targets: list[dict], source: str) -> bool:
        if not self._hardware_connected:
            self._set_status("Servo preview unavailable · PCA9685 is not connected")
            return False
        if not self._servo_power:
            self._set_status("Servo power is disabled · enable PWM before previewing")
            return False
        if self._movement_active:
            self._set_status("Servo preview blocked · movement is active")
            return False
        self._preview_cancel.clear()
        with self._preview_condition:
            self._preview_request = {"targets": targets, "source": source}
            self._range_busy = source == "range"
            self._preview_condition.notify()
        if source == "range":
            self.rangeTestChanged.emit()
        return True

    def _write_preview_pwm(self, channel: int, pulse: int) -> bool:
        """Write under the movement lock and recover one lost I2C session."""
        if self._servoctl is None:
            return False
        lock = self._servoctl._movement_command_lock
        if not lock.acquire(timeout=0.35):
            return False
        try:
            with self._io_lock:
                if self._servoctl.set_servo_pwm(channel, pulse):
                    return True
            # set_servo_pwm discards a controller after its bounded retries.
            # Reopen once but leave PWM off.  Re-enabling writes the complete
            # calibrated pose; retrying only this joint could drop support on
            # every other joint and destabilize the robot.
            if not self._reconnect_hardware():
                return False
            return False
        finally:
            lock.release()

    def _take_latest_preview(self) -> dict | None:
        with self._preview_condition:
            if self._preview_request is not None:
                request = self._preview_request
                self._preview_request = None
                return request
        return None

    def _preview_worker(self) -> None:
        """Coalesce drag events and ramp one servo command at a time."""
        while True:
            with self._preview_condition:
                while self._preview_request is None and not self._preview_stop:
                    self._preview_condition.wait()
                if self._preview_stop:
                    return
                request = self._preview_request
                self._preview_request = None

            targets = list(request.get("targets") or [])
            source = str(request.get("source") or "calibration")
            failed = False
            superseded = False
            for target in targets:
                channel = int(target["channel"])
                desired = int(target["pulse"])
                servo_id = str(target.get("servo_id") or "")
                current = int(self._servoctl.servo_positions.get(channel, desired))
                needs_write = channel not in self._servoctl._channels_initialized

                while (
                    (current != desired or needs_write)
                    and not self._preview_stop
                    and not self._preview_cancel.is_set()
                ):
                    replacement_request = self._take_latest_preview()
                    if replacement_request is not None:
                        replacement_targets = list(replacement_request.get("targets") or [])
                        if not replacement_targets:
                            continue
                        replacement = replacement_targets[-1]
                        if int(replacement["channel"]) != channel:
                            with self._preview_condition:
                                self._preview_request = replacement_request
                                self._preview_condition.notify()
                            superseded = True
                            break
                        desired = int(replacement["pulse"])
                        servo_id = str(replacement.get("servo_id") or servo_id)
                        source = str(replacement_request.get("source") or source)

                    delta = desired - current
                    step = max(-self._preview_step_ticks, min(self._preview_step_ticks, delta))
                    next_pulse = current + step
                    if not self._write_preview_pwm(channel, next_pulse):
                        failed = True
                        break
                    current = next_pulse
                    needs_write = False
                    self._servoctl.servo_positions[channel] = current
                    if source == "range" and servo_id == self._range_servo_id:
                        start, end = self._effective_endpoints(servo_id)
                        span = end - start
                        self._range_applied_percent = (
                            round((current - start) * 100 / span) if span else 0
                        )
                        self.rangeTestChanged.emit()
                    time.sleep(self._preview_interval)
                if failed:
                    break
                if superseded:
                    break

            if source == "range":
                self._range_busy = False
                self.rangeTestChanged.emit()
            if failed:
                if not self._hardware_connected:
                    self._set_status("Servo preview failed · controller is offline")
                elif self._servo_power:
                    self._set_status("Servo preview failed · controller is busy")

    def _target_pulse(self, servo_id: str, offset: int) -> int:
        definition = SERVO_DEFINITIONS[servo_id]
        base = definition.get("preview_base")
        if base is None:
            base = self._config_int(definition["preview_key"], 300)
        return int(base) + int(definition.get("preview_sign", 1)) * offset

    def _offset_is_safe(self, servo_id: str, offset: int) -> bool:
        minimum, maximum = self._offset_bounds(servo_id)
        return minimum <= offset <= maximum

    def _preview_servo(self, servo_id: str) -> bool:
        definition = SERVO_DEFINITIONS[servo_id]
        offset = int(self._servos[servo_id]["value"])
        pulse = self._target_pulse(servo_id, offset)
        if not self._hardware_connected:
            return True
        return self._queue_preview_targets([
            {"channel": definition["channel"], "pulse": pulse, "servo_id": servo_id}
        ], "calibration")

    def _preview_all(self) -> bool:
        servo_ids = list(self._servos)
        if not self._arms_present():
            servo_ids = [servo_id for servo_id in servo_ids if "_height" in servo_id or "_leg" in servo_id]
        if not self._hardware_connected:
            return True
        targets = []
        for servo_id in servo_ids:
            definition = SERVO_DEFINITIONS[servo_id]
            targets.append({
                "channel": definition["channel"],
                "pulse": self._target_pulse(servo_id, int(self._servos[servo_id]["value"])),
                "servo_id": servo_id,
            })
        return self._queue_preview_targets(targets, "calibration")

    def _apply_servo_value(self, servo_id: str, raw_value: float, final: bool) -> None:
        servo = self._servos.get(servo_id)
        if not servo:
            return
        if self._movement_active:
            self._set_status("Calibration blocked · movement is active")
            return
        value = max(servo["minimum"], min(servo["maximum"], round(raw_value)))
        if not self._offset_is_safe(servo_id, value):
            self._set_status(
                f"Blocked {servo['label'].title()} · allowed offset is "
                f"{servo['minimum']:+d} to {servo['maximum']:+d}"
            )
            if final:
                self.servosChanged.emit()
            return
        if servo["value"] == value and final:
            self._preview_servo(servo_id)
            return
        old_value = servo["value"]
        servo["value"] = value
        if not self._preview_servo(servo_id):
            servo["value"] = old_value
            if final:
                self.servosChanged.emit()
            return
        self._diagnostic_phase = -1
        self.diagnosticsChanged.emit()
        if final:
            self.servosChanged.emit()
        self.rangeTestChanged.emit()
        self._set_dirty(self._servos != self._saved_servos)
        if final:
            mode = "Moved" if self._hardware_connected else "Previewing"
            pulse = self._target_pulse(servo_id, value)
            self._set_status(
                f"{mode} {servo['label'].title()}: {value:+d} ticks · "
                f"PWM {pulse} · not saved"
            )

    @Slot(str, float)
    def previewServoValue(self, servo_id: str, raw_value: float) -> None:
        self._apply_servo_value(servo_id, raw_value, final=False)

    @Slot(str, float)
    def setServoValue(self, servo_id: str, raw_value: float) -> None:
        self._apply_servo_value(servo_id, raw_value, final=True)

    @Slot(str, int)
    def adjustServo(self, servo_id: str, delta: int) -> None:
        servo = self._servos.get(servo_id)
        if servo:
            self.setServoValue(servo_id, servo["value"] + delta)

    @Slot(str)
    def selectRangeServo(self, servo_id: str) -> None:
        if servo_id not in SERVO_DEFINITIONS or servo_id == self._range_servo_id:
            return
        is_arm = "_height" not in servo_id and "_leg" not in servo_id
        if is_arm and not self._arms_present():
            self._set_status("Range test unavailable · arms_present is disabled")
            return
        self._preview_cancel.set()
        with self._preview_condition:
            self._preview_request = None
        self._range_armed = False
        self._range_busy = False
        self._range_servo_id = servo_id
        definition = SERVO_DEFINITIONS[servo_id]
        current = int(
            self._servoctl.servo_positions.get(
                definition["channel"], self._range_target_pulse(servo_id, 50)
            )
        ) if self._servoctl is not None else self._range_target_pulse(servo_id, 50)
        start, end = self._effective_endpoints(servo_id)
        span = end - start
        percent = round((current - start) * 100 / span) if span else 0
        self._range_percent = max(0, min(100, percent))
        self._range_applied_percent = self._range_percent
        self.rangeTestChanged.emit()
        self._set_status(f"Selected range test · {SERVO_DEFINITIONS[servo_id]['label'].title()}")

    @Slot(bool)
    def setRangeTestArmed(self, armed: bool) -> None:
        armed = bool(armed)
        if armed:
            if not self._hardware_connected or not self._servo_power:
                self._set_status("Enable PWM before arming the range test")
                return
            if self._movement_active:
                self._set_status("Range test blocked · movement is active")
                return
        else:
            self._preview_cancel.set()
            with self._preview_condition:
                self._preview_request = None
            self._range_busy = False
        self._range_armed = armed
        self.rangeTestChanged.emit()
        self._set_status(
            f"Range test {'armed' if armed else 'disarmed'} · "
            f"{self.selectedRangeServoLabel.title()}"
        )

    def _apply_range_percent(self, raw_percent: float, final: bool) -> None:
        if not self._range_armed:
            if final:
                self._set_status("Range test is disarmed · arm the selected servo first")
            return
        if self._movement_active:
            self._set_status("Range test blocked · movement is active")
            return
        percent = max(0, min(100, round(raw_percent)))
        self._range_percent = percent
        pulse = self._range_target_pulse(self._range_servo_id, percent)
        definition = SERVO_DEFINITIONS[self._range_servo_id]
        queued = self._queue_preview_targets([
            {
                "channel": definition["channel"],
                "pulse": pulse,
                "servo_id": self._range_servo_id,
            }
        ], "range")
        self.rangeTestChanged.emit()
        if final and queued:
            self._set_status(
                f"Range target · {self.selectedRangeServoLabel.title()} · "
                f"{percent}% · PWM {pulse}"
            )

    @Slot(float)
    def previewRangePosition(self, raw_percent: float) -> None:
        self._apply_range_percent(raw_percent, final=False)

    @Slot(float)
    def setRangePosition(self, raw_percent: float) -> None:
        self._apply_range_percent(raw_percent, final=True)

    @Slot(int)
    def nudgeRangePosition(self, delta: int) -> None:
        self.setRangePosition(self._range_percent + int(delta))

    def _run_movement_worker(self, movement: str, label: str) -> None:
        try:
            from modules import module_movements
            action = getattr(module_movements, movement, None)
            if not callable(action):
                raise KeyError(f"Unknown movement: {movement}")
            completed = action()
            if completed is False or self._servoctl.movement_stop_requested():
                self._set_status(f"Movement stopped · {label}")
            else:
                self._set_status(f"Movement complete · {label}")
        except Exception as exc:
            self._set_status(f"Movement failed · {exc}")
        finally:
            self._movement_active = False
            self.stateChanged.emit()

    @Slot(str)
    def runMovement(self, movement: str) -> None:
        from modules.module_movement_registry import MOVEMENTS

        metadata = MOVEMENTS.get(movement)
        if metadata is None:
            self._set_status(f"Unknown movement · {movement}")
            return
        label = metadata["name"]
        if not self._hardware_connected:
            self._set_status(f"Mock movement · {label}")
            return
        if not self._servo_power:
            self._set_status("Movement blocked · servo power is disabled")
            return
        if self._movement_active:
            self._set_status("Movement already in progress")
            return
        self._preview_cancel.set()
        with self._preview_condition:
            self._preview_request = None
        self._range_armed = False
        self._range_busy = False
        self._movement_active = True
        self._diagnostic_phase = -1
        self.diagnosticsChanged.emit()
        self.stateChanged.emit()
        self.rangeTestChanged.emit()
        self._set_status(f"Running movement · {label}")
        threading.Thread(
            target=self._run_movement_worker,
            args=(movement, label),
            daemon=True,
        ).start()

    @Slot(str)
    def setMovementCategory(self, category: str) -> None:
        if category not in MOVEMENT_CATEGORIES or category == self._movement_category:
            return
        self._movement_category = category
        self.movementsChanged.emit()

    @Slot(str)
    def setDiagnosticDirection(self, direction: str) -> None:
        direction = direction.lower()
        if direction not in ("forward", "backward"):
            return
        if self._movement_active:
            self._set_status("Finish or stop the active movement before changing direction")
            return
        if self._diagnostic_phase > 0:
            self._set_status("Return the diagnostic to neutral before changing direction")
            return
        if direction == self._diagnostic_direction:
            return
        self._diagnostic_direction = direction
        self._diagnostic_phase = -1
        self.diagnosticsChanged.emit()
        self._set_status(f"Diagnostic direction: {direction} · start from neutral")

    def _complete_mock_diagnostic_phase(self, index: int, name: str) -> None:
        self._diagnostic_phase = index
        self.diagnosticsChanged.emit()
        self._set_status(f"Mock diagnostic phase {index} · {name}")

    def _run_diagnostic_prefix(self, index: int, name: str) -> None:
        """Replay the original movement continuously through ``index``."""
        if not self._hardware_connected:
            self._complete_mock_diagnostic_phase(index, name)
            return
        if not self._servo_power:
            self._set_status("Diagnostic blocked · servo power is disabled")
            return
        if self._movement_active:
            self._set_status("Movement already in progress")
            return

        self._preview_cancel.set()
        with self._preview_condition:
            self._preview_request = None
        self._range_armed = False
        self._range_busy = False
        self.rangeTestChanged.emit()
        phases = body_swing_diagnostic_phases(
            self._diagnostic_direction,
            self._arms_present(),
        )
        selected_phases = [phase for phase in phases if phase["index"] <= index]

        def diagnostic_worker() -> None:
            def replay_prefix() -> None:
                # This initial neutral call and every subsequent speed factor
                # match the original step_forward/step_backward routines.
                self._servoctl.move_legs_original(50, 50, 50, 50, 0.9)
                for phase in selected_phases:
                    self._servoctl.move_legs_original(*phase["pose"], phase["speed"])

            guarded_replay = self._servoctl.movement_command(replay_prefix)
            try:
                completed = guarded_replay()
                if completed:
                    self._diagnostic_phase = index
                    if index == 0:
                        self._set_status("Original diagnostic reset · neutral held")
                    else:
                        self._set_status(f"Original sequence held at phase {index} · {name}")
                else:
                    self._set_status(f"Original sequence stopped · {name}")
            except Exception as exc:
                self._set_status(f"Original sequence diagnostic failed · {exc}")
            finally:
                self._movement_active = False
                self.stateChanged.emit()
                self.diagnosticsChanged.emit()

        self._movement_active = True
        self.stateChanged.emit()
        if index == 0:
            self._set_status("Resetting original diagnostic to neutral")
        else:
            self._set_status(f"Replaying original sequence through phase {index} · {name}")
        threading.Thread(target=diagnostic_worker, daemon=True).start()

    @Slot()
    def startDiagnostic(self) -> None:
        self._run_diagnostic_prefix(0, "NEUTRAL START")

    @Slot()
    def runOriginalStepReplay(self) -> None:
        """Run the exact original single-step movement without diagnostic holds."""
        self.runMovement("step_forward")

    @Slot(int)
    def runDiagnosticPhase(self, index: int) -> None:
        if self._diagnostic_phase < 0:
            self._set_status("Reset the diagnostic to neutral before selecting a replay phase")
            return
        phases = body_swing_diagnostic_phases(
            self._diagnostic_direction,
            self._arms_present(),
        )
        phase = next((item for item in phases if item["index"] == index), None)
        if phase is None:
            self._set_status(f"Unknown diagnostic phase · {index}")
            return
        self._run_diagnostic_prefix(phase["index"], phase["name"])

    @Slot()
    def stopMovement(self) -> None:
        if self._hardware_connected and self._servoctl is not None:
            self._servoctl.request_movement_stop()
        self._set_status("Stopping movement safely…")

    @Slot()
    def disableServos(self) -> None:
        if self._power_transition:
            return
        self._preview_cancel.set()
        with self._preview_condition:
            self._preview_request = None
        self._servo_power = False
        self._range_armed = False
        self._range_busy = False
        self._diagnostic_phase = -1
        self._power_transition = self._hardware_connected and self._servoctl is not None
        self.stateChanged.emit()
        self.diagnosticsChanged.emit()
        self.rangeTestChanged.emit()
        if not self._power_transition:
            self._set_status("Servo output disabled")
            return

        self._servoctl.request_movement_stop()
        self._set_status("Stopping movement and disabling servo output…")

        def disable_worker() -> None:
            lock = self._servoctl._movement_command_lock
            acquired = lock.acquire(timeout=6.0)
            try:
                if not acquired:
                    self._set_status("Servo disable timed out · use the hardware power switch")
                    return
                with self._io_lock:
                    self._servoctl.disable_all_servos()
                self._set_status("Servo output disabled")
            finally:
                if acquired:
                    lock.release()
                self._power_transition = False
                self.stateChanged.emit()

        threading.Thread(target=disable_worker, name="servo-disable", daemon=True).start()

    @Slot()
    def enableServos(self) -> None:
        if self._power_transition:
            self._set_status("Wait for servo power shutdown to finish")
            return
        if not self._hardware_connected or self._servoctl is None:
            self._servo_power = False
            self.stateChanged.emit()
            self._set_status(f"Servo output unavailable · {self._hardware_error or 'PCA9685 not connected'}")
            return
        if self._movement_active:
            self._set_status("Finish or stop the active movement before enabling servo output")
            return
        self._servo_power = True
        self._diagnostic_phase = -1
        self.stateChanged.emit()
        self.diagnosticsChanged.emit()
        self.rangeTestChanged.emit()
        if self._preview_all():
            self._set_status("Servo output enabled · calibrated positions written to PCA9685")
        else:
            try:
                self._servoctl.disable_all_servos()
            finally:
                self._servo_power = False
                self.stateChanged.emit()

    @Slot()
    def resetPositions(self) -> None:
        if not self._hardware_connected:
            self._set_status("Mock reset · calibration values were not changed")
            return
        if not self._servo_power:
            self._set_status("Neutral position blocked · servo power is disabled")
            return
        if self._movement_active:
            self._set_status("Movement already in progress")
            return

        self._preview_cancel.set()
        with self._preview_condition:
            self._preview_request = None
        self._range_armed = False
        self._range_busy = False
        self.rangeTestChanged.emit()
        def reset_worker() -> None:
            guarded_reset = self._servoctl.movement_command(self._servoctl.reset_positions)
            completed = False
            try:
                completed = guarded_reset()
                self._set_status("Neutral position restored" if completed else "Neutral reset stopped")
            except Exception as exc:
                self._set_status(f"Neutral reset failed · {exc}")
            finally:
                self._movement_active = False
                self.stateChanged.emit()
                if completed:
                    self._diagnostic_phase = 0
                    self.diagnosticsChanged.emit()

        self._movement_active = True
        self.stateChanged.emit()
        self._set_status("Moving all servos to their configured neutral positions")
        threading.Thread(target=reset_worker, daemon=True).start()

    def _write_offsets(self) -> None:
        if self._config_path is None:
            raise FileNotFoundError("config.ini was not found in the project or src directory")
        lines = self._config_path.read_text(encoding="utf-8").splitlines(keepends=True)
        values = {
            SERVO_DEFINITIONS[servo_id]["config"]: int(servo["value"])
            for servo_id, servo in self._servos.items()
        }
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
        backup = self._config_path.with_name("config.calibration-backup.ini")
        shutil.copy2(self._config_path, backup)
        temporary = self._config_path.with_suffix(self._config_path.suffix + ".tmp")
        temporary.write_text("".join(lines), encoding="utf-8", newline="")
        temporary.replace(self._config_path)

    @Slot()
    def saveCalibration(self) -> None:
        try:
            self._write_offsets()
            self._servo_config = _read_servo_config(self._config_path)
            if self._hardware_connected:
                from modules import module_config
                module_config._config_cache = None
                self._servoctl.refresh_config()
            self._saved_servos = deepcopy(self._servos)
            self._set_dirty(False)
            self._set_status(f"Calibration saved to {self._config_path.name}")
        except Exception as exc:
            self._set_status(f"Calibration save failed · {exc}")

    @Slot()
    def revertCalibration(self) -> None:
        self._preview_cancel.set()
        self._servos = deepcopy(self._saved_servos)
        self.servosChanged.emit()
        self.rangeTestChanged.emit()
        self._set_dirty(False)
        self._preview_all()
        self._set_status("Unsaved calibration changes reverted")

    @Slot(str)
    def setProfile(self, profile: str) -> None:
        if not profile or profile == self._profile:
            return
        self._profile = profile
        self.profileChanged.emit()
        self._set_status(f"Active profile: {profile}")

    def shutdown(self) -> None:
        self._preview_cancel.set()
        with self._preview_condition:
            self._preview_stop = True
            self._preview_request = None
            self._preview_condition.notify_all()
        if self._preview_thread is not None and self._preview_thread.is_alive():
            self._preview_thread.join(timeout=2.0)

        if self._servoctl is not None:
            try:
                # cleanup waits for the movement lock before disabling and
                # deinitializing hardware, so close cannot race a final write.
                self._servoctl.cleanup(timeout=6.0)
            except Exception as exc:
                print(f"[SERVO TESTER] Shutdown warning: {exc}", file=sys.stderr)
        self._pca = None
        self._i2c = None
        self._hardware_connected = False
        self._servo_power = False


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("TARS Servo Calibration")
    app.setOrganizationName("TARS-AI")
    engine = QQmlApplicationEngine()
    controller = ServoCalibrationController()
    app.aboutToQuit.connect(controller.shutdown)
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "ServoCalibration.qml")))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if ARGS.diagnostic:
        window.setProperty("currentPage", 3)
    if ARGS.window_size:
        try:
            width, height = (int(part) for part in ARGS.window_size.lower().split("x", 1))
            window.setWidth(width)
            window.setHeight(height)
        except (TypeError, ValueError):
            print("--window-size must look like 800x480", file=sys.stderr)
            return 2
    if ARGS.fullscreen:
        window.showFullScreen()
    if ARGS.screenshot:
        screenshot_path = ARGS.screenshot.resolve()
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            pointer = shiboken6.getCppPointer(window)[0]
            quick_window = shiboken6.wrapInstance(pointer, QQuickWindow)
            image = quick_window.grabWindow()
            if not image.save(str(screenshot_path)):
                print(f"Unable to save screenshot: {screenshot_path}", file=sys.stderr)
                app.exit(2)
                return
            print(f"Screenshot saved: {screenshot_path}")
            app.quit()

        QTimer.singleShot(1200, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
