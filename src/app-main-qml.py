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
    parser.add_argument(
        "--app",
        choices=("clock", "dashboard", "system-health", "eyes", "avatar", "remote", "audio"),
        help="open one registered app directly for UI testing",
    )
    parser.add_argument(
        "--panel",
        choices=("apps", "menu"),
        help="open a launcher panel directly for UI testing",
    )
    parser.add_argument("--screenshot", type=Path, help="save a screenshot and exit")
    return parser.parse_args()


ARGS = _parse_args()

# The TARS controls provide their own visuals. Basic is the portable Qt Quick
# style intended for full customization and avoids host-native style drift.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

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
    avatarChanged = Signal()
    remoteChanged = Signal()
    dashboardChanged = Signal()

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
        self._remote_state = "ready"
        self._remote_status = "Connected to TARS-NET"
        self._remote_url = ""
        self._remote_error = ""
        self._wifi_networks = [
            {"ssid": "TARS-NET", "signal": 92, "security": "WPA2", "in_use": True},
            {"ssid": "ENDURANCE", "signal": 68, "security": "WPA2", "in_use": False},
        ]
        self._dashboard_loading = False
        self._dashboard_error = ""
        self._dashboard_weather = {
            "temperature": 63,
            "feelsLike": 61,
            "humidity": 54,
            "wind": 9,
            "condition": "Partly cloudy",
            "unit": "°F",
            "location": "Chicago",
        }
        self._dashboard_forecast = [
            {"day": "MON", "high": 66, "low": 48, "rain": 10, "condition": "Clear"},
            {"day": "TUE", "high": 62, "low": 46, "rain": 35, "condition": "Cloudy"},
            {"day": "WED", "high": 59, "low": 44, "rain": 70, "condition": "Rain"},
            {"day": "THU", "high": 64, "low": 47, "rain": 15, "condition": "Clear"},
            {"day": "FRI", "high": 68, "low": 51, "rain": 10, "condition": "Clear"},
        ]
        self._dashboard_news = [
            {"kind": "NEWS", "title": "Robotics team completes a new autonomous field test", "detail": "The latest trial focused on navigation and perception.", "meta": "TECH", "date": ""},
            {"kind": "NEWS", "title": "Astronomers publish new deep-space observations", "detail": "Researchers shared results from a multi-year survey.", "meta": "SCIENCE", "date": ""},
        ]
        self._dashboard_calendar = [
            {"kind": "CALENDAR", "title": "TARS calibration session", "detail": "Workshop", "meta": "TODAY · 6:30 PM", "date": ""},
            {"kind": "CALENDAR", "title": "Project review", "detail": "Lab", "meta": "TOMORROW · 10:00 AM", "date": ""},
        ]
        self._dashboard_quote = {
            "text": "We're explorers, not caretakers.",
            "author": "Interstellar",
        }

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

    @Property(str, notify=clockChanged)
    def currentTimeSeconds(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

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

    @Property(float, constant=True)
    def batteryVoltage(self) -> float:
        return 11.74

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

    @Property(int, notify=telemetryChanged)
    def wifiSignal(self) -> int:
        return 92 if self._wifi_online else 0

    @Property(int, notify=telemetryChanged)
    def memoryPercent(self) -> int:
        return 42

    @Property(int, notify=telemetryChanged)
    def diskPercent(self) -> int:
        return 31

    @Property(str, notify=telemetryChanged)
    def uptimeText(self) -> str:
        return "3h 18m"

    @Property(int, notify=telemetryChanged)
    def processThreads(self) -> int:
        return 14

    @Property("QVariantList", notify=telemetryChanged)
    def hardwareDiagnostics(self) -> list[dict[str, object]]:
        return [
            {"label": "SERVO CONTROLLER", "value": "ONLINE", "state": "ok", "detail": "PCA9685 servo controller detected"},
            {"label": "BATTERY SENSOR", "value": "ONLINE", "state": "ok", "detail": "INA260 voltage and current sensor detected"},
            {"label": "CAMERA", "value": "CONFIGURED", "state": "info", "detail": "Camera will initialize on first use"},
            {"label": "MICROPHONE", "value": "ONLINE", "state": "ok", "detail": "Shared audio input and wake-word stream"},
        ]

    @Property("QVariantList", notify=telemetryChanged)
    def softwareDiagnostics(self) -> list[dict[str, object]]:
        return [
            {"label": "RUNTIME", "value": "READY", "state": "ok", "detail": "ALL SYSTEMS OPERATIONAL"},
            {"label": "SPEECH INPUT", "value": "OPENAI", "state": "ok", "detail": "GPT Live transcription"},
            {"label": "VOICE OUTPUT", "value": "ELEVENLABS", "state": "ok", "detail": "Configured text-to-speech backend"},
            {"label": "LANGUAGE MODEL", "value": "OPENAI", "state": "info", "detail": "Configured conversational model"},
        ]

    @Property(bool, notify=dashboardChanged)
    def dashboardLoading(self) -> bool:
        return self._dashboard_loading

    @Property(str, notify=dashboardChanged)
    def dashboardError(self) -> str:
        return self._dashboard_error

    @Property("QVariantMap", notify=dashboardChanged)
    def dashboardWeather(self) -> dict[str, object]:
        return self._dashboard_weather

    @Property("QVariantList", notify=dashboardChanged)
    def dashboardForecast(self) -> list[dict[str, object]]:
        return self._dashboard_forecast

    @Property("QVariantList", notify=dashboardChanged)
    def dashboardNews(self) -> list[dict[str, object]]:
        return self._dashboard_news

    @Property("QVariantList", notify=dashboardChanged)
    def dashboardCalendar(self) -> list[dict[str, object]]:
        return self._dashboard_calendar

    @Property("QVariantList", notify=dashboardChanged)
    def dashboardFeed(self) -> list[dict[str, object]]:
        var_feed = []
        for index in range(max(len(self._dashboard_news), len(self._dashboard_calendar))):
            if index < len(self._dashboard_calendar):
                var_feed.append(self._dashboard_calendar[index])
            if index < len(self._dashboard_news):
                var_feed.append(self._dashboard_news[index])
        return var_feed

    @Property("QVariantMap", notify=dashboardChanged)
    def dashboardQuote(self) -> dict[str, object]:
        return self._dashboard_quote

    @Property(str, constant=True)
    def dashboardLocation(self) -> str:
        return "Chicago"

    @Property(str, notify=dashboardChanged)
    def dashboardLastUpdated(self) -> str:
        return datetime.now().strftime("%I:%M %p").lstrip("0")

    @Property(bool, constant=True)
    def dashboardCalendarConfigured(self) -> bool:
        return True

    @Property(str, constant=True)
    def dashboardConfigFile(self) -> str:
        return "dashboard.ini"

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

    @Property(str, constant=True)
    def avatarFrameSource(self) -> str:
        path = ROOT / "character" / "TARS" / "images" / "neutral" / "animation" / "TARS_neutral_nottalking_eyes_open.png"
        return QUrl.fromLocalFile(str(path)).toString() if path.is_file() else ""

    @Property(str, constant=True)
    def avatarCharacter(self) -> str:
        return "TARS"

    @Property(str, constant=True)
    def avatarEmotion(self) -> str:
        return "NEUTRAL"

    @Property(str, notify=remoteChanged)
    def remoteState(self) -> str:
        return self._remote_state

    @Property(str, notify=remoteChanged)
    def remoteStatus(self) -> str:
        return self._remote_status

    @Property(str, notify=remoteChanged)
    def remoteUrl(self) -> str:
        return self._remote_url

    @Property(str, notify=remoteChanged)
    def remoteError(self) -> str:
        return self._remote_error

    @Property("QVariantList", notify=remoteChanged)
    def wifiNetworks(self) -> list[dict[str, object]]:
        return self._wifi_networks

    @Property(bool, constant=True)
    def calibrationActive(self) -> bool:
        return False

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
    def launchServoCalibration(self) -> None:
        self._set_notice("Mock servo calibration handoff · no hardware action was taken", 5000)

    @Slot()
    def refreshRemoteAccess(self) -> None:
        self._remote_state = "ready"
        self._remote_status = "Connected to TARS-NET"
        self._remote_url = ""
        self.remoteChanged.emit()

    @Slot()
    def scanWifiNetworks(self) -> None:
        self._remote_state = "networks"
        self._remote_status = "2 networks found"
        self.remoteChanged.emit()

    @Slot(str, str)
    def connectWifiNetwork(self, ssid: str, _password: str) -> None:
        self._remote_state = "ready"
        self._remote_status = f"Connected to {ssid} (prototype)"
        self.remoteChanged.emit()

    @Slot()
    def startRemoteAccess(self) -> None:
        self._remote_state = "active"
        self._remote_status = "Remote tunnel is online (prototype)"
        self._remote_url = "https://tars-demo.example"
        self.remoteChanged.emit()

    @Slot()
    def stopRemoteAccess(self) -> None:
        self._remote_state = "idle"
        self._remote_status = "Remote access stopped (prototype)"
        self._remote_url = ""
        self.remoteChanged.emit()

    @Slot()
    def refreshDashboard(self) -> None:
        self._dashboard_loading = True
        self.dashboardChanged.emit()

        def finish_refresh() -> None:
            self._dashboard_loading = False
            self.dashboardChanged.emit()
            self._set_notice("Dashboard data refreshed (prototype)")

        QTimer.singleShot(450, finish_refresh)

    @Slot()
    def nextDashboardQuote(self) -> None:
        quotes = [
            {"text": "We're explorers, not caretakers.", "author": "Interstellar"},
            {"text": "Somewhere, something incredible is waiting to be known.", "author": "Carl Sagan"},
            {"text": "Mankind was born on Earth. It was never meant to die here.", "author": "Interstellar"},
        ]
        current = next(
            (index for index, quote in enumerate(quotes) if quote["text"] == self._dashboard_quote.get("text")),
            -1,
        )
        self._dashboard_quote = quotes[(current + 1) % len(quotes)]
        self.dashboardChanged.emit()

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
    def requestRestart(self) -> None:
        self._set_notice("Mock restart requested · no process action was taken", 5000)

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
    engine.warnings.connect(
        lambda warnings: [
            print(f"QML: {warning.toString()}", file=sys.stderr)
            for warning in warnings
        ]
    )
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
    if ARGS.app or ARGS.panel:
        scene = window.findChild(QObject, "scene")
        if scene is None:
            print("Unable to find the QML scene for preview", file=sys.stderr)
            return 2
    if ARGS.app:
        scene.setProperty("activeAppId", ARGS.app)
        scene.setProperty("appReturnMode", "apps")
        scene.setProperty("overlayMode", "app")
    elif ARGS.panel:
        scene.setProperty("overlayMode", ARGS.panel)
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
