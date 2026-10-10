"""PySide6/QML servo calibration UI for TARS.

On a Raspberry Pi this app uses the project's existing PCA9685 servo module.
On other computers it automatically uses a safe mock backend. Pass ``--mock``
on the Pi to explore the interface without moving hardware.
"""

from __future__ import annotations

import argparse
import configparser
import os
import sys
import threading
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

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
import shiboken6


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


def _servo(servo_id: str, value: int) -> dict:
    definition = SERVO_DEFINITIONS[servo_id]
    is_arm = "_height" not in servo_id and "_leg" not in servo_id
    return {
        "id": servo_id,
        "label": definition["label"],
        "value": value,
        "minimum": -90 if is_arm else -50,
        "maximum": 90 if is_arm else 50,
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

    def __init__(self) -> None:
        super().__init__()
        self._config_path = _find_config_path()
        self._servo_config = _read_servo_config(self._config_path)
        self._servoctl = None
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

        self._servos = {}
        for servo_id, definition in SERVO_DEFINITIONS.items():
            raw = self._servo_config.get(definition["config"], "0")
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = 0
            self._servos[servo_id] = _servo(servo_id, value)

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

    def _connect_hardware(self) -> None:
        try:
            import board
            import busio
            from adafruit_pca9685 import PCA9685
            import modules.module_servoctl as servoctl

            # Match the hardware path used by the original, known-working
            # servotester: open a fresh bus/controller for this standalone app
            # and explicitly give that controller to module_servoctl.
            self._i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(self._i2c, address=0x40)
            self._pca.frequency = 50
            servoctl.pca = self._pca
            servoctl._channels_initialized.clear()
            self._servoctl = servoctl
            self._hardware_connected = self._pca is not None
            if not self._hardware_connected:
                raise RuntimeError("PCA9685 was not detected")
            # Begin from a known, torque-free state. POWER ON will issue fresh
            # PWM writes to every installed servo.
            servoctl.disable_all_servos()
        except Exception as exc:
            self._hardware_error = str(exc)
            self._hardware_connected = False
            print(f"[SERVO TESTER] Hardware mode unavailable: {exc}", file=sys.stderr)

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

    @Property(bool, constant=True)
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
        return "ARMS PROFILE" if self._arms_present() else "NO-ARMS PROFILE"

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
            )
            item["completed"] = item["index"] <= self._diagnostic_phase
            item["next"] = item["index"] == self._diagnostic_phase + 1
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

    def _arms_present(self) -> bool:
        return str(self._servo_config.get("arms_present", "false")).lower() in (
            "1", "true", "yes", "on"
        )

    def _target_pulse(self, servo_id: str, offset: int) -> int:
        definition = SERVO_DEFINITIONS[servo_id]
        base = definition.get("preview_base")
        if base is None:
            base = self._config_int(definition["preview_key"], 300)
        return int(base) + int(definition.get("preview_sign", 1)) * offset

    def _offset_is_safe(self, servo_id: str, offset: int) -> bool:
        definition = SERVO_DEFINITIONS[servo_id]
        sign = int(definition.get("limit_sign", 1))
        return all(
            10 <= self._config_int(key, 300) + sign * offset <= 600
            for key in definition["limits"]
        )

    def _preview_servo(self, servo_id: str) -> bool:
        if not self._hardware_connected:
            return True
        if not self._servo_power:
            self._set_status("Servo power is disabled · enable servos before previewing")
            return False
        definition = SERVO_DEFINITIONS[servo_id]
        offset = int(self._servos[servo_id]["value"])
        pulse = self._target_pulse(servo_id, offset)
        try:
            if not self._servoctl.set_servo_pwm(definition["channel"], pulse):
                raise RuntimeError("I2C write failed")
            self._servoctl.servo_positions[definition["channel"]] = pulse
            return True
        except Exception as exc:
            self._set_status(f"Servo preview failed · {exc}")
            return False

    def _preview_all(self) -> bool:
        servo_ids = list(self._servos)
        if not self._arms_present():
            servo_ids = [servo_id for servo_id in servo_ids if "_height" in servo_id or "_leg" in servo_id]
        for servo_id in servo_ids:
            if not self._preview_servo(servo_id):
                return False
        return True

    @Slot(str, float)
    def setServoValue(self, servo_id: str, raw_value: float) -> None:
        servo = self._servos.get(servo_id)
        if not servo:
            return
        value = max(servo["minimum"], min(servo["maximum"], round(raw_value)))
        if not self._offset_is_safe(servo_id, value):
            self._set_status(f"Blocked {servo['label'].title()} · pulse would leave safe range 10–600")
            self.servosChanged.emit()
            return
        if servo["value"] == value:
            self._preview_servo(servo_id)
            return
        old_value = servo["value"]
        servo["value"] = value
        if not self._preview_servo(servo_id):
            servo["value"] = old_value
            self.servosChanged.emit()
            return
        self._diagnostic_phase = -1
        self.diagnosticsChanged.emit()
        self.servosChanged.emit()
        self._set_dirty(self._servos != self._saved_servos)
        mode = "Moved" if self._hardware_connected else "Previewing"
        self._set_status(f"{mode} {servo['label'].title()}: {value:+d} ticks · not saved")

    @Slot(str, int)
    def adjustServo(self, servo_id: str, delta: int) -> None:
        servo = self._servos.get(servo_id)
        if servo:
            self.setServoValue(servo_id, servo["value"] + delta)

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
        self._movement_active = True
        self._diagnostic_phase = -1
        self.diagnosticsChanged.emit()
        self.stateChanged.emit()
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

    def _run_diagnostic_pose(
        self,
        index: int,
        name: str,
        pose: tuple[int, int, int, int],
        duration: float,
    ) -> None:
        if not self._hardware_connected:
            self._complete_mock_diagnostic_phase(index, name)
            return
        if not self._servo_power:
            self._set_status("Diagnostic blocked · servo power is disabled")
            return
        if self._movement_active:
            self._set_status("Movement already in progress")
            return

        def diagnostic_worker() -> None:
            def apply_pose() -> None:
                self._servoctl.move_legs_timed(*pose, duration=duration)

            guarded_pose = self._servoctl.movement_command(apply_pose)
            try:
                completed = guarded_pose()
                if completed:
                    self._diagnostic_phase = index
                    self._set_status(f"Diagnostic phase {index} held · {name}")
                else:
                    self._set_status(f"Diagnostic phase stopped · {name}")
            except Exception as exc:
                self._set_status(f"Diagnostic phase failed · {exc}")
            finally:
                self._movement_active = False
                self.stateChanged.emit()
                self.diagnosticsChanged.emit()

        self._movement_active = True
        self.stateChanged.emit()
        self._set_status(f"Applying diagnostic phase {index} · {name}")
        threading.Thread(target=diagnostic_worker, daemon=True).start()

    @Slot()
    def startDiagnostic(self) -> None:
        self._run_diagnostic_pose(
            0,
            "NEUTRAL START",
            (50, 50, 50, 50),
            0.40,
        )

    @Slot(int)
    def runDiagnosticPhase(self, index: int) -> None:
        expected = self._diagnostic_phase + 1
        if self._diagnostic_phase < 0:
            self._set_status("Start the diagnostic at neutral before applying phase 1")
            return
        if index != expected:
            self._set_status(f"Apply phase {expected} next · diagnostic phases must stay in order")
            return
        phases = body_swing_diagnostic_phases(
            self._diagnostic_direction,
            self._arms_present(),
        )
        phase = next((item for item in phases if item["index"] == index), None)
        if phase is None:
            self._set_status(f"Unknown diagnostic phase · {index}")
            return
        self._run_diagnostic_pose(
            phase["index"],
            phase["name"],
            phase["pose"],
            phase["duration"],
        )

    @Slot()
    def stopMovement(self) -> None:
        if self._hardware_connected and self._servoctl is not None:
            self._servoctl.request_movement_stop()
        self._set_status("Stopping movement safely…")

    @Slot()
    def disableServos(self) -> None:
        if self._hardware_connected:
            self._servoctl.request_movement_stop()
            self._servoctl.disable_all_servos()
        self._servo_power = False
        self._diagnostic_phase = -1
        self.stateChanged.emit()
        self.diagnosticsChanged.emit()
        self._set_status("Servo output disabled")

    @Slot()
    def enableServos(self) -> None:
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
        temporary = self._config_path.with_suffix(self._config_path.suffix + ".tmp")
        temporary.write_text("".join(lines), encoding="utf-8", newline="")
        temporary.replace(self._config_path)

    @Slot()
    def saveCalibration(self) -> None:
        try:
            self._write_offsets()
            self._servo_config = _read_servo_config(self._config_path)
            if self._hardware_connected:
                import modules.module_config as module_config
                module_config._config_cache = None
                self._servoctl.refresh_config()
            self._saved_servos = deepcopy(self._servos)
            self._set_dirty(False)
            self._set_status(f"Calibration saved to {self._config_path.name}")
        except Exception as exc:
            self._set_status(f"Calibration save failed · {exc}")

    @Slot()
    def revertCalibration(self) -> None:
        self._servos = deepcopy(self._saved_servos)
        self.servosChanged.emit()
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
        if self._hardware_connected:
            try:
                self._servoctl.request_movement_stop()
                self._servoctl.disable_all_servos()
            except Exception as exc:
                print(f"[SERVO TESTER] Shutdown warning: {exc}", file=sys.stderr)
        if self._pca is not None:
            try:
                self._pca.deinit()
            except Exception:
                pass


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
        window.setProperty("currentPage", 2)
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
