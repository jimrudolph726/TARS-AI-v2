"""Hardware-safe PySide6/QML prototype for the main TARS touchscreen.

The controller in this module intentionally simulates TARS state, telemetry,
conversation data, and actions.  It does not import any robot hardware modules,
so the prototype can be exercised on Windows or a Raspberry Pi without moving
servos, opening the camera, or starting the speech/LLM stack.

The QObject surface is intentionally close to a production bridge: QML owns
presentation and interaction while Python exposes observable state and slots.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TARS main-interface QML prototype")
    parser.add_argument("--fullscreen", action="store_true", help="open full screen")
    parser.add_argument("--autoplay", action="store_true", help="cycle mock TARS states automatically")
    parser.add_argument("--rotation", type=int, choices=(0, 90, 180, 270), default=90,
                        help="rotate the logical portrait UI for a mounted display")
    parser.add_argument("--width", type=int, default=480, help="window width when not full screen")
    parser.add_argument("--height", type=int, default=720, help="window height when not full screen")
    parser.add_argument("--screenshot", type=Path, help="save a screenshot and exit")
    return parser.parse_args()


ARGS = _parse_args()

# Qt reads these values during import/application construction.  Software
# rendering makes deterministic screenshots possible on headless test hosts.
if ARGS.screenshot and "QT_QPA_PLATFORM" not in os.environ:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import (  # noqa: E402
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QFontDatabase, QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402
import shiboken6  # noqa: E402


ROOT = Path(__file__).resolve().parent


class ConversationModel(QAbstractListModel):
    """Small production-shaped model used by the conversation ListView."""

    SpeakerRole = Qt.UserRole + 1
    MessageRole = Qt.UserRole + 2
    TimeRole = Qt.UserRole + 3
    IsTarsRole = Qt.UserRole + 4

    def __init__(self) -> None:
        super().__init__()
        message_time = datetime.now().strftime("%I:%M %p").lstrip("0")
        self._items: list[dict[str, object]] = [
            {
                "speaker": "YOU",
                "message": "What's our status?",
                "time": message_time,
                "isTars": False,
            },
            {
                "speaker": "TARS",
                "message": "All systems nominal.",
                "time": message_time,
                "isTars": True,
            },
        ]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: ANN001
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        role_map = {
            self.SpeakerRole: "speaker",
            self.MessageRole: "message",
            self.TimeRole: "time",
            self.IsTarsRole: "isTars",
        }
        key = role_map.get(role)
        return item.get(key) if key else None

    def roleNames(self) -> dict[int, bytes]:  # noqa: N802
        return {
            self.SpeakerRole: b"speaker",
            self.MessageRole: b"message",
            self.TimeRole: b"messageTime",
            self.IsTarsRole: b"isTars",
        }

    def add_message(self, speaker: str, message: str, is_tars: bool) -> None:
        # Remove first so model notifications are never nested.
        if len(self._items) >= 8:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._items.pop(0)
            self.endRemoveRows()
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(
            {
                "speaker": speaker,
                "message": message,
                "time": datetime.now().strftime("%I:%M %p").lstrip("0"),
                "isTars": is_tars,
            }
        )
        self.endInsertRows()


class MainInterfaceController(QObject):
    """Simulated state bridge exposed to the QML presentation."""

    clockChanged = Signal()
    stateChanged = Signal()
    telemetryChanged = Signal()
    mutedChanged = Signal()
    noticeChanged = Signal()
    audioChanged = Signal()
    cameraChanged = Signal()

    STATES = (
        ("LISTENING", "TARS READY"),
        ("THINKING", "PROCESSING REQUEST"),
        ("SPEAKING", "RESPONSE ACTIVE"),
        ("IDLE", "STANDING BY"),
    )

    def __init__(self, autoplay: bool = False) -> None:
        super().__init__()
        self._state_index = 0
        self._battery = 81
        self._cpu_temperature = 48
        self._wifi_online = True
        self._muted = False
        self._notice = ""
        self._conversation = ConversationModel()
        self._telemetry_phase = 0.0
        self._audio_phase = 0.0
        self._audio_levels = [0.0] * 35
        self._camera_active = False
        self._camera_error = ""

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self.clockChanged.emit)
        self._clock_timer.start()

        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.setInterval(2200)
        self._telemetry_timer.timeout.connect(self._update_telemetry)
        self._telemetry_timer.start()

        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._clear_notice)

        self._autoplay_timer = QTimer(self)
        self._autoplay_timer.setInterval(4200)
        self._autoplay_timer.timeout.connect(self.cycleState)
        if autoplay:
            self._autoplay_timer.start()

        self._audio_timer = QTimer(self)
        self._audio_timer.setInterval(55)
        self._audio_timer.timeout.connect(self._update_demo_audio)
        self._audio_timer.start()

    @Property(str, notify=clockChanged)
    def currentTime(self) -> str:
        return datetime.now().strftime("%I:%M %p").lstrip("0")

    @Property(str, notify=clockChanged)
    def currentDate(self) -> str:
        return datetime.now().strftime("%b %d %Y").upper()

    @Property(str, notify=stateChanged)
    def tarsState(self) -> str:
        return self.STATES[self._state_index][0]

    @Property(str, notify=stateChanged)
    def stateDetail(self) -> str:
        return self.STATES[self._state_index][1]

    @Property(int, notify=telemetryChanged)
    def batteryPercent(self) -> int:
        return self._battery

    @Property(bool, constant=True)
    def batteryAvailable(self) -> bool:
        return True

    @Property(int, notify=telemetryChanged)
    def cpuTemperature(self) -> int:
        return self._cpu_temperature

    @Property(bool, constant=True)
    def cpuAvailable(self) -> bool:
        return True

    @Property(bool, notify=telemetryChanged)
    def wifiOnline(self) -> bool:
        return self._wifi_online

    @Property(str, notify=telemetryChanged)
    def wifiSsid(self) -> str:
        return "TARS-NET" if self._wifi_online else ""

    @Property(bool, constant=True)
    def runtimeReady(self) -> bool:
        return True

    @Property(str, constant=True)
    def runtimeStatus(self) -> str:
        return "PROTOTYPE READY"

    @Property(bool, constant=True)
    def uiVisible(self) -> bool:
        return True

    @Property(bool, constant=True)
    def overlayVisible(self) -> bool:
        return False

    @Property(str, constant=True)
    def overlaySource(self) -> str:
        return ""

    @Property(bool, notify=mutedChanged)
    def muted(self) -> bool:
        return self._muted

    @Property(str, notify=noticeChanged)
    def noticeText(self) -> str:
        return self._notice

    @Property("QVariantList", notify=audioChanged)
    def audioLevels(self) -> list[float]:
        return self._audio_levels

    @Property(float, notify=audioChanged)
    def audioLevel(self) -> float:
        return max(self._audio_levels, default=0.0)

    @Property(bool, notify=cameraChanged)
    def cameraActive(self) -> bool:
        return self._camera_active

    @Property(bool, notify=cameraChanged)
    def cameraReady(self) -> bool:
        return False

    @Property(str, notify=cameraChanged)
    def cameraError(self) -> str:
        return self._camera_error

    @Property(int, notify=cameraChanged)
    def cameraFrameRevision(self) -> int:
        return 0

    @Property(QObject, constant=True)
    def conversationModel(self) -> QObject:
        return self._conversation

    def _set_notice(self, text: str, timeout_ms: int = 3200) -> None:
        self._notice = text
        self.noticeChanged.emit()
        self._notice_timer.start(timeout_ms)

    @Slot()
    def _clear_notice(self) -> None:
        if self._notice:
            self._notice = ""
            self.noticeChanged.emit()

    @Slot()
    def cycleState(self) -> None:
        self._state_index = (self._state_index + 1) % len(self.STATES)
        self.stateChanged.emit()
        self._set_notice(f"Mock TARS state: {self.tarsState.title()}")

    @Slot(str)
    def setState(self, state: str) -> None:
        requested = state.strip().upper()
        for index, (name, _) in enumerate(self.STATES):
            if name == requested and index != self._state_index:
                self._state_index = index
                self.stateChanged.emit()
                self._set_notice(f"Mock TARS state: {name.title()}")
                return

    @Slot()
    def toggleMute(self) -> None:
        self._muted = not self._muted
        self.mutedChanged.emit()
        self._set_notice("Microphone muted" if self._muted else "Microphone active")

    @Slot(str)
    def activateFeature(self, feature: str) -> None:
        self._set_notice(f"{feature} opened in safe prototype mode")

    @Slot()
    def openCamera(self) -> None:
        self._camera_active = True
        self._camera_error = "Camera feed is available in the live Raspberry Pi runtime"
        self.cameraChanged.emit()

    @Slot()
    def closeCamera(self) -> None:
        self._camera_active = False
        self.cameraChanged.emit()

    @Slot(str)
    def launchApp(self, app_name: str) -> None:
        self._set_notice(f"Mock app selected: {app_name}")

    @Slot()
    def addDemoExchange(self) -> None:
        self._conversation.add_message("YOU", "Run a quick diagnostic.", False)
        self._conversation.add_message("TARS", "Diagnostic complete. No faults detected.", True)
        self._set_notice("Demo conversation added")

    @Slot()
    def requestPower(self) -> None:
        self._set_notice("Mock shutdown requested · no system action was taken", 5000)

    @Slot()
    def requestShutdown(self) -> None:
        self.requestPower()

    @Slot()
    def exitProgram(self) -> None:
        QGuiApplication.quit()

    @Slot()
    def toggleWifi(self) -> None:
        self._wifi_online = not self._wifi_online
        self.telemetryChanged.emit()
        self._set_notice("Wi-Fi online" if self._wifi_online else "Wi-Fi offline (simulated)")

    @Slot()
    def _update_telemetry(self) -> None:
        self._telemetry_phase += 0.55
        self._cpu_temperature = 48 + round(3 * math.sin(self._telemetry_phase))
        self.telemetryChanged.emit()

    @Slot()
    def _update_demo_audio(self) -> None:
        self._audio_phase += 0.18
        self._audio_levels = [
            max(0.03, abs(math.sin(self._audio_phase + index * 0.57)) * (0.3 + 0.7 * math.sin(index / 34 * math.pi)))
            for index in range(35)
        ]
        self.audioChanged.emit()


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("TARS Main Interface Prototype")
    app.setOrganizationName("TARS-AI")

    def load_font(filename: str, fallback: str) -> str:
        font_id = QFontDatabase.addApplicationFont(str(ROOT / "modules" / "UI" / filename))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        return families[0] if families else fallback

    # Bundle the same fonts used by the existing Pygame interface so rendering
    # does not depend on desktop-only font packages on either Windows or Pi OS.
    display_font = load_font("pixelmix.ttf", "Sans Serif")
    mono_font = load_font("mono.ttf", "Monospace")

    engine = QQmlApplicationEngine()
    controller = MainInterfaceController(autoplay=ARGS.autoplay)
    context = engine.rootContext()
    context.setContextProperty("controller", controller)
    context.setContextProperty("displayRotation", ARGS.rotation)
    context.setContextProperty("initialWindowWidth", max(320, ARGS.width))
    context.setContextProperty("initialWindowHeight", max(320, ARGS.height))
    context.setContextProperty("displayFontFamily", display_font)
    context.setContextProperty("monoFontFamily", mono_font)
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "main" / "TarsMain.qml")))

    if not engine.rootObjects():
        return 1

    window = engine.rootObjects()[0]
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

        QTimer.singleShot(1400, capture)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
