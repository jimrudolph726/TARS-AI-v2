"""Native PySide6/QML interface controller for TARS-AI.

Qt owns the application's main thread.  The robot runtime calls the public
methods on :class:`TarsUIController` from worker threads; those methods emit
queued Qt signals so every model and property mutation still happens on the
GUI thread.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from PySide6.QtCore import (
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
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


class ConversationModel(QAbstractListModel):
    """Conversation history exposed directly to the QML ``ListView``."""

    SpeakerRole = Qt.UserRole + 1
    MessageRole = Qt.UserRole + 2
    TimeRole = Qt.UserRole + 3
    IsTarsRole = Qt.UserRole + 4

    def __init__(self, maximum_rows: int = 40, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._items: list[dict[str, object]] = []
        self._maximum_rows = maximum_rows

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
        if len(self._items) >= self._maximum_rows:
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

    def update_last_message(self, message: str) -> None:
        if not self._items:
            self.add_message("TARS", message, True)
            return
        row = len(self._items) - 1
        self._items[row]["message"] = message
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self.MessageRole])

    def update_speaker(self, old_speaker: str, text: str, new_speaker: str) -> None:
        for row in range(len(self._items) - 1, -1, -1):
            item = self._items[row]
            if item["speaker"] == old_speaker and item["message"] == text:
                item["speaker"] = new_speaker
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [self.SpeakerRole])
                return


class CameraImageProvider(QQuickImageProvider):
    """Serve the controller's latest camera frame to QML without disk I/O."""

    def __init__(self, controller: "TarsUIController") -> None:
        super().__init__(QQuickImageProvider.Image)
        self._controller = controller

    def requestImage(self, _image_id, size, requested_size):  # noqa: N802, ANN001
        image = self._controller.camera_image()
        if image.isNull():
            image = QImage(640, 480, QImage.Format_RGB888)
            image.fill(Qt.black)
        if requested_size.isValid():
            image = image.scaled(
                requested_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class TarsUIController(QObject):
    """Live, thread-safe state surface consumed by ``TarsMain.qml``."""

    clockChanged = Signal()
    stateChanged = Signal()
    telemetryChanged = Signal()
    mutedChanged = Signal()
    noticeChanged = Signal()
    runtimeChanged = Signal()
    visibilityChanged = Signal()
    overlayChanged = Signal()
    silenceChanged = Signal()
    audioChanged = Signal()
    cameraChanged = Signal()

    runtimeStopped = Signal()

    _messageRequested = Signal(str, str, str)
    _streamRequested = Signal(str)
    _speakerRequested = Signal(str, str, str)
    _stateRequested = Signal(str)
    _noticeRequested = Signal(str, int)
    _runtimeRequested = Signal(str, bool)
    _visibilityRequested = Signal(bool)
    _overlayRequested = Signal(str, int)
    _telemetryRequested = Signal(object)
    _silenceRequested = Signal(float)
    _cameraStartedRequested = Signal(object, object, str)
    _exitRequested = Signal()
    _shutdownRequested = Signal()

    _STATE_DETAILS = {
        "BOOTING": "INITIALIZING SYSTEMS",
        "STANDBY": "TARS READY",
        "LISTENING": "AWAITING COMMAND",
        "THINKING": "PROCESSING REQUEST",
        "TALKING": "RESPONSE ACTIVE",
        "SPEAKING": "RESPONSE ACTIVE",
    }

    def __init__(self, base_dir: Path, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._base_dir = Path(base_dir)
        self._conversation = ConversationModel(parent=self)
        self._state = "BOOTING"
        self._battery_percent = 0
        self._battery_voltage = 0.0
        self._battery_available = False
        self._cpu_temperature = 0
        self._cpu_available = False
        self._wifi_online = False
        self._wifi_ssid = ""
        self._wifi_signal = 0
        self._muted = False
        self._notice = ""
        self._runtime_ready = False
        self._runtime_status = "STARTING TARS RUNTIME"
        self._ui_visible = True
        self._overlay_source = ""
        self._overlay_visible = False
        self._silence_progress = 0.0
        self._running = True
        self._stopped = False

        self._audio_levels = [0.0] * 35
        self._pending_audio_levels = [0.0] * 35
        self._audio_peak = 0.025
        self._audio_lock = threading.Lock()
        self._audio_stream = None

        self._camera_module = None
        self._camera_active = False
        self._camera_starting = False
        self._camera_ready = False
        self._camera_error = ""
        self._camera_frame = QImage()
        self._camera_frame_revision = 0
        self._camera_lock = threading.Lock()

        self._battery_source = None
        self._cpu_source = None
        self._stt_manager = None
        self._request_stop: Optional[Callable[[], None]] = None
        self._request_shutdown: Optional[Callable[[], None]] = None
        self._source_lock = threading.Lock()
        self._wifi_stop = threading.Event()

        self._messageRequested.connect(self._apply_message)
        self._streamRequested.connect(self._conversation.update_last_message)
        self._speakerRequested.connect(self._conversation.update_speaker)
        self._stateRequested.connect(self._apply_state)
        self._noticeRequested.connect(self._apply_notice)
        self._runtimeRequested.connect(self._apply_runtime_status)
        self._visibilityRequested.connect(self._apply_visibility)
        self._overlayRequested.connect(self._apply_overlay)
        self._telemetryRequested.connect(self._apply_network_telemetry)
        self._silenceRequested.connect(self._apply_silence)
        self._cameraStartedRequested.connect(self._apply_camera_started)
        self._exitRequested.connect(self.exitProgram)
        self._shutdownRequested.connect(self.requestShutdown)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self.clockChanged.emit)
        self._clock_timer.start()

        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.setInterval(2000)
        self._telemetry_timer.timeout.connect(self._poll_local_telemetry)
        self._telemetry_timer.start()

        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._clear_notice)

        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.timeout.connect(self._clear_overlay)

        self._audio_timer = QTimer(self)
        self._audio_timer.setInterval(40)
        self._audio_timer.timeout.connect(self._publish_audio_levels)
        self._audio_timer.start()

        self._camera_timer = QTimer(self)
        self._camera_timer.setInterval(100)
        self._camera_timer.timeout.connect(self._refresh_camera_frame)

        threading.Thread(
            target=self._wifi_poll_loop,
            name="QMLWiFiTelemetry",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._start_audio_visualizer,
            name="QMLAudioVisualizer",
            daemon=True,
        ).start()

    @Property(str, notify=clockChanged)
    def currentTime(self) -> str:
        return datetime.now().strftime("%I:%M %p").lstrip("0")

    @Property(str, notify=clockChanged)
    def currentDate(self) -> str:
        return datetime.now().strftime("%b %d %Y").upper()

    @Property(str, notify=stateChanged)
    def tarsState(self) -> str:
        return "SPEAKING" if self._state == "TALKING" else self._state

    @Property(str, notify=stateChanged)
    def stateDetail(self) -> str:
        return self._STATE_DETAILS.get(self._state, "SYSTEM ACTIVE")

    @Property(int, notify=telemetryChanged)
    def batteryPercent(self) -> int:
        return self._battery_percent

    @Property(float, notify=telemetryChanged)
    def batteryVoltage(self) -> float:
        return self._battery_voltage

    @Property(bool, notify=telemetryChanged)
    def batteryAvailable(self) -> bool:
        return self._battery_available

    @Property(int, notify=telemetryChanged)
    def cpuTemperature(self) -> int:
        return self._cpu_temperature

    @Property(bool, notify=telemetryChanged)
    def cpuAvailable(self) -> bool:
        return self._cpu_available

    @Property(bool, notify=telemetryChanged)
    def wifiOnline(self) -> bool:
        return self._wifi_online

    @Property(str, notify=telemetryChanged)
    def wifiSsid(self) -> str:
        return self._wifi_ssid

    @Property(int, notify=telemetryChanged)
    def wifiSignal(self) -> int:
        return self._wifi_signal

    @Property(bool, notify=mutedChanged)
    def muted(self) -> bool:
        return self._muted

    @Property(str, notify=noticeChanged)
    def noticeText(self) -> str:
        return self._notice

    @Property(bool, notify=runtimeChanged)
    def runtimeReady(self) -> bool:
        return self._runtime_ready

    @Property(str, notify=runtimeChanged)
    def runtimeStatus(self) -> str:
        return self._runtime_status

    @Property(bool, notify=visibilityChanged)
    def uiVisible(self) -> bool:
        return self._ui_visible

    @Property(str, notify=overlayChanged)
    def overlaySource(self) -> str:
        return self._overlay_source

    @Property(bool, notify=overlayChanged)
    def overlayVisible(self) -> bool:
        return self._overlay_visible

    @Property(float, notify=silenceChanged)
    def silenceProgress(self) -> float:
        return self._silence_progress

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
        return self._camera_ready

    @Property(str, notify=cameraChanged)
    def cameraError(self) -> str:
        return self._camera_error

    @Property(int, notify=cameraChanged)
    def cameraFrameRevision(self) -> int:
        return self._camera_frame_revision

    @Property(QObject, constant=True)
    def conversationModel(self) -> QObject:
        return self._conversation

    @property
    def running(self) -> bool:
        return self._running

    def bind_runtime(
        self,
        request_stop: Callable[[], None],
        request_shutdown: Callable[[], None],
    ) -> None:
        self._request_stop = request_stop
        self._request_shutdown = request_shutdown

    def attach_sources(self, battery=None, cpu=None, stt=None) -> None:
        with self._source_lock:
            if battery is not None:
                self._battery_source = battery
            if cpu is not None:
                self._cpu_source = cpu
            if stt is not None:
                self._stt_manager = stt

    def _start_audio_visualizer(self) -> None:
        """Subscribe to the shared microphone hub used by STT."""
        try:
            from modules.module_mic import open_native_stream

            stream = open_native_stream(callback=self._audio_callback)
            stream.start()
            self._audio_stream = stream
        except Exception as exc:
            print(f"WARNING: QML microphone visualizer unavailable: {exc}")

    def _audio_callback(self, indata, _frames, _time_info, _status) -> None:
        """Reduce a live mic chunk to the 35 samples drawn by QML."""
        if self._muted:
            levels = np.zeros(35, dtype=np.float32)
        else:
            audio = np.asarray(indata[:, 0], dtype=np.float32)
            if audio.size == 0:
                return
            absolute = np.abs(audio)
            frame_peak = float(np.percentile(absolute, 97))
            self._audio_peak = max(0.015, self._audio_peak * 0.965, frame_peak)
            indices = np.linspace(0, audio.size - 1, 35, dtype=np.int32)
            levels = np.clip(absolute[indices] / self._audio_peak, 0.0, 1.0) ** 0.68

        with self._audio_lock:
            self._pending_audio_levels = levels.tolist()

    @Slot()
    def _publish_audio_levels(self) -> None:
        with self._audio_lock:
            target = list(self._pending_audio_levels)
        smoothed = []
        for current, requested in zip(self._audio_levels, target):
            blend = 0.72 if requested > current else 0.34
            smoothed.append(current + (requested - current) * blend)
        self._audio_levels = smoothed
        self.audioChanged.emit()

    def camera_image(self) -> QImage:
        with self._camera_lock:
            return self._camera_frame.copy()

    def _camera_start_worker(self) -> None:
        try:
            from modules.UI.module_ui_camera import CameraModule

            camera = self._camera_module or CameraModule(640, 480, use_camera_module=True)
            if camera.picam2 is None:
                raise RuntimeError("Raspberry Pi camera was not detected")
            if not camera.running:
                camera.start_camera()

            deadline = time.monotonic() + 6.0
            frame = None
            while time.monotonic() < deadline and self._camera_active:
                frame = camera.capture_rgb_array()
                if frame is not None:
                    break
                time.sleep(0.05)
            if frame is None:
                raise RuntimeError("camera did not produce a frame")

            image = self._array_to_qimage(frame)
            self._cameraStartedRequested.emit(camera, image, "")
        except Exception as exc:
            self._cameraStartedRequested.emit(None, QImage(), str(exc))

    @staticmethod
    def _array_to_qimage(frame) -> QImage:  # noqa: ANN001
        rgb = np.ascontiguousarray(frame, dtype=np.uint8)
        height, width, channels = rgb.shape
        return QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format_RGB888,
        ).copy()

    @Slot()
    def openCamera(self) -> None:
        self._camera_active = True
        self._camera_error = ""
        self.cameraChanged.emit()
        if self._camera_ready:
            self._camera_timer.start()
            return
        if self._camera_starting:
            return
        self._camera_starting = True
        threading.Thread(
            target=self._camera_start_worker,
            name="QMLCameraStartup",
            daemon=True,
        ).start()

    @Slot()
    def closeCamera(self) -> None:
        self._camera_active = False
        self._camera_timer.stop()
        self.cameraChanged.emit()

    @Slot(object, object, str)
    def _apply_camera_started(self, camera, image, error: str) -> None:  # noqa: ANN001
        self._camera_starting = False
        if error:
            self._camera_ready = False
            self._camera_error = error
            self._apply_notice(f"CAMERA ERROR: {error}", 5000)
        else:
            self._camera_module = camera
            self._camera_ready = True
            with self._camera_lock:
                self._camera_frame = image
            self._camera_frame_revision += 1
            if self._camera_active:
                self._camera_timer.start()
        self.cameraChanged.emit()

    @Slot()
    def _refresh_camera_frame(self) -> None:
        if not self._camera_active or not self._camera_ready or self._camera_module is None:
            return
        try:
            frame = self._camera_module.capture_rgb_array()
            if frame is None:
                return
            image = self._array_to_qimage(frame)
            with self._camera_lock:
                self._camera_frame = image
            self._camera_frame_revision += 1
            self.cameraChanged.emit()
        except Exception as exc:
            self._camera_error = str(exc)
            self._camera_ready = False
            self._camera_timer.stop()
            self.cameraChanged.emit()

    def update_data(self, source: str, message: str, category: str = "INFO") -> None:
        self._messageRequested.emit(str(source), str(message), str(category))

    def update_streaming_data(self, value: str) -> None:
        self._streamRequested.emit(str(value))

    def update_message_speaker(self, old_speaker: str, text: str, new_speaker: str) -> None:
        self._speakerRequested.emit(str(old_speaker), str(text), str(new_speaker))

    def set_tars_status(self, status: str) -> None:
        self._stateRequested.emit(str(status))

    def set_runtime_status(self, status: str, ready: bool = False) -> None:
        self._runtimeRequested.emit(str(status), ready)

    def notify_runtime_stopped(self) -> None:
        self.runtimeStopped.emit()

    def pause(self) -> None:
        """Compatibility with motion callbacks; Qt rendering needs no pause."""

    def resume(self) -> None:
        """Compatibility with motion callbacks; Qt rendering needs no resume."""

    def hide(self) -> None:
        self._visibilityRequested.emit(False)

    def show(self) -> None:
        self._visibilityRequested.emit(True)

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._running = False
        self._wifi_stop.set()
        self._audio_timer.stop()
        self._camera_timer.stop()
        if self._audio_stream is not None:
            try:
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None
        if self._camera_module is not None:
            try:
                self._camera_module.stop()
            except Exception:
                pass

    def join(self, timeout=None) -> None:  # noqa: ANN001
        """Qt owns the main thread, so there is no UI worker to join."""

    def deactivate_screensaver(self) -> None:
        self.show()

    def show_overlay_image(self, image_path: str, duration: int = 8) -> None:
        path = Path(image_path).expanduser().resolve()
        self._overlayRequested.emit(QUrl.fromLocalFile(str(path)).toString(), int(duration * 1000))

    def silence(self, progress: float = 0) -> None:
        self._silenceRequested.emit(float(progress))

    def save_memory(self) -> None:
        self._noticeRequested.emit("MEMORY COMMITTED", 1800)

    def think(self) -> None:
        self.set_tars_status("THINKING")

    def exit_program(self) -> None:
        self._exitRequested.emit()

    def initiate_shutdown(self) -> None:
        self._shutdownRequested.emit()

    @Slot()
    def toggleMute(self) -> None:
        with self._source_lock:
            stt = self._stt_manager
        try:
            if self._muted:
                if stt:
                    stt.resume()
                self._muted = False
                message = "MICROPHONE ACTIVE"
            else:
                if stt:
                    stt.pause()
                self._muted = True
                message = "MICROPHONE MUTED"
            self.mutedChanged.emit()
            self._apply_notice(message, 2600)
        except Exception as exc:
            self._apply_notice(f"MICROPHONE ERROR: {exc}", 4200)

    @Slot(str)
    def activateFeature(self, feature: str) -> None:
        if feature.strip().lower() == "camera":
            self.openCamera()
        else:
            self._apply_notice(f"{feature.upper()} SELECTED", 2400)

    @Slot(str)
    def launchApp(self, app_name: str) -> None:
        normalized = app_name.strip().upper()
        if normalized == "SERVO TEST":
            script = self._base_dir / "app-servotester-qml.py"
            try:
                subprocess.Popen([sys.executable, str(script), "--fullscreen"], cwd=self._base_dir)
                self._apply_notice("SERVO TESTER LAUNCHED", 2800)
            except Exception as exc:
                self._apply_notice(f"SERVO TESTER FAILED: {exc}", 4500)
            return
        self._apply_notice(f"{normalized} APP IS NOT MIGRATED YET", 3200)

    @Slot()
    def exitProgram(self) -> None:
        self._apply_notice("STOPPING TARS", 5000)
        if self._request_stop:
            self._request_stop()
        else:
            self.runtimeStopped.emit()

    @Slot()
    def requestShutdown(self) -> None:
        self._apply_notice("SHUTDOWN REQUESTED", 5000)
        if self._request_shutdown:
            self._request_shutdown()
        else:
            self.runtimeStopped.emit()

    @Slot(str, str, str)
    def _apply_message(self, source: str, message: str, category: str) -> None:
        source = source.strip() or "SYSTEM"
        category_upper = category.upper()
        source_upper = source.upper()
        non_tars_sources = {"YOU", "USER", "SYSTEM", "INFO", "LOAD", "ERROR", "WARNING"}
        is_tars = (
            source_upper == "TARS"
            or category_upper == "TARS"
            or (source_upper == category_upper and source_upper not in non_tars_sources)
        )
        self._conversation.add_message(source_upper, message, is_tars)

    @Slot(str)
    def _apply_state(self, status: str) -> None:
        normalized = status.strip().upper()
        if normalized and normalized != self._state:
            self._state = normalized
            self.stateChanged.emit()

    @Slot(str, int)
    def _apply_notice(self, text: str, timeout_ms: int = 3200) -> None:
        self._notice = text
        self.noticeChanged.emit()
        self._notice_timer.start(max(500, timeout_ms))

    @Slot()
    def _clear_notice(self) -> None:
        if self._notice:
            self._notice = ""
            self.noticeChanged.emit()

    @Slot(str, bool)
    def _apply_runtime_status(self, status: str, ready: bool) -> None:
        self._runtime_status = status
        self._runtime_ready = ready
        self.runtimeChanged.emit()

    @Slot(bool)
    def _apply_visibility(self, visible: bool) -> None:
        if visible != self._ui_visible:
            self._ui_visible = visible
            self.visibilityChanged.emit()

    @Slot(str, int)
    def _apply_overlay(self, source: str, duration_ms: int) -> None:
        self._overlay_source = source
        self._overlay_visible = True
        self.overlayChanged.emit()
        self._overlay_timer.start(max(500, duration_ms))

    @Slot()
    def _clear_overlay(self) -> None:
        if self._overlay_visible:
            self._overlay_visible = False
            self.overlayChanged.emit()

    @Slot(float)
    def _apply_silence(self, progress: float) -> None:
        self._silence_progress = progress
        self.silenceChanged.emit()

    @Slot()
    def _poll_local_telemetry(self) -> None:
        changed = False
        with self._source_lock:
            battery = self._battery_source
            cpu = self._cpu_source

        if battery is not None:
            try:
                status = battery.get_battery_status()
                self._battery_available = bool(status.get("sensor_initialized", False))
                self._battery_percent = int(status.get("normalized_percentage", 0))
                self._battery_voltage = float(status.get("voltage", 0.0))
                changed = True
            except Exception:
                self._battery_available = False

        if cpu is not None:
            try:
                self._cpu_available = bool(getattr(cpu, "sensor_available", False))
                self._cpu_temperature = round(float(cpu.get_temperature()))
                changed = True
            except Exception:
                self._cpu_available = False

        if changed:
            self.telemetryChanged.emit()

    def _wifi_poll_loop(self) -> None:
        while not self._wifi_stop.wait(8):
            try:
                from modules.module_wifi import get_wifi_status

                status = get_wifi_status()
                self._telemetryRequested.emit(status)
            except Exception:
                self._telemetryRequested.emit(
                    {"mode": "disconnected", "ssid": None, "signal": 0}
                )

    @Slot(object)
    def _apply_network_telemetry(self, status: object) -> None:
        if not isinstance(status, dict):
            return
        mode = str(status.get("mode", "disconnected"))
        self._wifi_online = mode not in ("disconnected", "unknown", "")
        self._wifi_ssid = str(status.get("ssid") or "")
        self._wifi_signal = int(status.get("signal") or 0)
        self.telemetryChanged.emit()

