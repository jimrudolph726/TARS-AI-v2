"""Desktop-safe PySide6/QML prototype for the TARS servo calibration UI.

This intentionally uses a mock backend.  It does not import board, busio,
PCA9685, or module_servoctl, so it is safe to run on a development computer.
The QObject API is shaped so a hardware controller can replace it later without
rewriting the QML presentation layer.
"""

from __future__ import annotations

import argparse
import os
import sys
from copy import deepcopy
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TARS servo calibration QML prototype")
    parser.add_argument("--fullscreen", action="store_true", help="open full screen")
    parser.add_argument("--screenshot", type=Path, help="save a screenshot and exit")
    return parser.parse_args()


ARGS = _parse_args()

# These make the automated screenshot path work without a display server.  They
# are set before importing Qt because Qt reads them during application startup.
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


def _servo(servo_id: str, label: str, value: int, minimum: int, maximum: int, unit: str) -> dict:
    return {
        "id": servo_id,
        "label": label,
        "value": value,
        "minimum": minimum,
        "maximum": maximum,
        "unit": unit,
    }


class ServoCalibrationController(QObject):
    """Mock state/controller exposed to QML through properties and slots."""

    servosChanged = Signal()
    stateChanged = Signal()
    statusChanged = Signal()
    profileChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._servos = {
            "left_height": _servo("left_height", "LEFT HEIGHT", -12, -50, 50, "mm"),
            "left_leg": _servo("left_leg", "LEFT LEG  (FORWARD / BACK)", 3, -50, 50, "mm"),
            "left_main": _servo("left_main", "LEFT MAIN ARM", 0, -90, 90, "°"),
            "left_forearm": _servo("left_forearm", "LEFT FOREARM", 0, -90, 90, "°"),
            "left_hand": _servo("left_hand", "LEFT HAND", 0, -90, 90, "°"),
            "right_height": _servo("right_height", "RIGHT HEIGHT", 7, -50, 50, "mm"),
            "right_leg": _servo("right_leg", "RIGHT LEG  (FORWARD / BACK)", -2, -50, 50, "mm"),
            "right_main": _servo("right_main", "RIGHT MAIN ARM", 0, -90, 90, "°"),
            "right_forearm": _servo("right_forearm", "RIGHT FOREARM", 0, -90, 90, "°"),
            "right_hand": _servo("right_hand", "RIGHT HAND", 0, -90, 90, "°"),
        }
        self._saved_servos = deepcopy(self._servos)
        self._dirty = False
        self._servo_power = True
        self._status = "Mock hardware online · controls are safe to explore"
        self._profile = "Default"
        self._battery = 81
        self._voltage = 11.74

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

    @Property(QUrl, constant=True)
    def tarsImageUrl(self) -> QUrl:
        image_path = PROJECT_ROOT / "media" / "2026-02-03 192140.png"
        return QUrl.fromLocalFile(str(image_path))

    def _set_status(self, message: str) -> None:
        self._status = message
        self.statusChanged.emit()

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty != dirty:
            self._dirty = dirty
            self.stateChanged.emit()

    @Slot(str, float)
    def setServoValue(self, servo_id: str, raw_value: float) -> None:
        servo = self._servos.get(servo_id)
        if not servo:
            return
        value = max(servo["minimum"], min(servo["maximum"], round(raw_value)))
        if servo["value"] == value:
            return
        servo["value"] = value
        self.servosChanged.emit()
        self._set_dirty(self._servos != self._saved_servos)
        self._set_status(f"Previewing {servo['label'].title()}: {value:+d}{servo['unit']}")

    @Slot(str, int)
    def adjustServo(self, servo_id: str, delta: int) -> None:
        servo = self._servos.get(servo_id)
        if servo:
            self.setServoValue(servo_id, servo["value"] + delta)

    @Slot(str)
    def runMovement(self, movement: str) -> None:
        if not self._servo_power:
            self._set_status("Movement blocked · servo power is disabled")
            return
        self._set_status(f"Simulated movement: {movement}")

    @Slot()
    def disableServos(self) -> None:
        self._servo_power = False
        self.stateChanged.emit()
        self._set_status("Servo power disabled · mock emergency stop engaged")

    @Slot()
    def enableServos(self) -> None:
        self._servo_power = True
        self.stateChanged.emit()
        self._set_status("Servo power enabled · mock controller active")

    @Slot()
    def resetPositions(self) -> None:
        for servo in self._servos.values():
            servo["value"] = 0
        self.servosChanged.emit()
        self._set_dirty(self._servos != self._saved_servos)
        self._set_status("All mock servos moved to neutral")

    @Slot()
    def saveCalibration(self) -> None:
        self._saved_servos = deepcopy(self._servos)
        self._set_dirty(False)
        self._set_status(f"Calibration saved to profile: {self._profile}")

    @Slot()
    def revertCalibration(self) -> None:
        self._servos = deepcopy(self._saved_servos)
        self.servosChanged.emit()
        self._set_dirty(False)
        self._set_status("Unsaved calibration changes reverted")

    @Slot(str)
    def setProfile(self, profile: str) -> None:
        if not profile or profile == self._profile:
            return
        self._profile = profile
        self.profileChanged.emit()
        self._set_status(f"Active mock profile: {profile}")


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("TARS Servo Calibration")
    app.setOrganizationName("TARS-AI")

    engine = QQmlApplicationEngine()
    controller = ServoCalibrationController()
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "ServoCalibration.qml")))

    if not engine.rootObjects():
        return 1

    window = engine.rootObjects()[0]
    if ARGS.fullscreen:
        window.showFullScreen()

    if ARGS.screenshot:
        screenshot_path = ARGS.screenshot.resolve()
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            # ApplicationWindow can be wrapped as QWindow rather than
            # QQuickWindow by PySide. Re-wrap the same C++ object as its actual
            # Qt Quick base class, then capture the scene graph directly.
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
