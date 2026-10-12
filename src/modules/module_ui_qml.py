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
    avatarChanged = Signal()
    remoteChanged = Signal()
    calibrationChanged = Signal()

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
    _remoteUpdateRequested = Signal(str, str, str, object)
    _calibrationStateRequested = Signal(bool)
    _exitRequested = Signal()
    _restartRequested = Signal()
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

        self._avatar_character = "TARS"
        self._avatar_emotion = "neutral"
        self._avatar_frame_source = ""

        self._remote_state = "idle"
        self._remote_status = "Remote access is ready"
        self._remote_url = ""
        self._remote_error = ""
        self._wifi_networks: list[dict[str, object]] = []
        self._calibration_active = False
        self._calibration_launching = False
        self._servo_tester_process = None
        self._servo_process_lock = threading.Lock()

        self._battery_source = None
        self._cpu_source = None
        self._stt_manager = None
        self._request_stop: Optional[Callable[[], None]] = None
        self._request_restart: Optional[Callable[[], None]] = None
        self._request_shutdown: Optional[Callable[[], None]] = None
        self._begin_servo_calibration: Optional[Callable[[], tuple[bool, str]]] = None
        self._end_servo_calibration: Optional[Callable[[], tuple[bool, str]]] = None
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
        self._remoteUpdateRequested.connect(self._apply_remote_update)
        self._calibrationStateRequested.connect(self._apply_calibration_state)
        self._exitRequested.connect(self.exitProgram)
        self._restartRequested.connect(self.requestRestart)
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

        self._avatar_timer = QTimer(self)
        self._avatar_timer.setInterval(120)
        self._avatar_timer.timeout.connect(self._refresh_avatar_frame)
        self._avatar_timer.start()
        self._load_avatar_character()
        self._refresh_avatar_frame()

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

    @Property(str, notify=clockChanged)
    def currentTimeSeconds(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

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

    @Property(str, notify=avatarChanged)
    def avatarFrameSource(self) -> str:
        return self._avatar_frame_source

    @Property(str, notify=avatarChanged)
    def avatarCharacter(self) -> str:
        return self._avatar_character

    @Property(str, notify=avatarChanged)
    def avatarEmotion(self) -> str:
        return self._avatar_emotion.upper()

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

    @Property(bool, notify=calibrationChanged)
    def calibrationActive(self) -> bool:
        return self._calibration_active

    @Property(QObject, constant=True)
    def conversationModel(self) -> QObject:
        return self._conversation

    @property
    def running(self) -> bool:
        return self._running

    def bind_runtime(
        self,
        request_stop: Callable[[], None],
        request_restart: Callable[[], None],
        request_shutdown: Callable[[], None],
        begin_servo_calibration: Callable[[], tuple[bool, str]],
        end_servo_calibration: Callable[[], tuple[bool, str]],
    ) -> None:
        self._request_stop = request_stop
        self._request_restart = request_restart
        self._request_shutdown = request_shutdown
        self._begin_servo_calibration = begin_servo_calibration
        self._end_servo_calibration = end_servo_calibration

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

    def _load_avatar_character(self) -> None:
        try:
            from modules.module_config import load_config

            char_cfg = load_config().get("CHAR", {})
            card_path = str(char_cfg.get("character_card_path", ""))
            self._avatar_character = Path(card_path).stem or str(
                char_cfg.get("character_name", "TARS")
            )
        except Exception:
            self._avatar_character = "TARS"

    @Slot()
    def _refresh_avatar_frame(self) -> None:
        module = sys.modules.get("modules.module_chatui")
        requested_emotion = str(getattr(module, "emotion", "neutral") or "neutral")
        requested_emotion = "".join(
            char for char in requested_emotion if char.isalnum() or char in "-_"
        ) or "neutral"
        animation_dir = (
            self._base_dir
            / "character"
            / self._avatar_character
            / "images"
            / requested_emotion
            / "animation"
        )
        if not animation_dir.is_dir():
            requested_emotion = "neutral"
            animation_dir = (
                self._base_dir
                / "character"
                / self._avatar_character
                / "images"
                / requested_emotion
                / "animation"
            )

        now = time.monotonic()
        talking = self._state in ("TALKING", "SPEAKING")
        blinking = int(now * 10) % 48 in (0, 1, 2)
        if talking:
            suffix = "talking_eyes_closed" if blinking else (
                "talking_eyes_open" if int(now * 10) % 2 else "nottalking_eyes_open"
            )
        else:
            suffix = "nottalking_eyes_closed" if blinking else "nottalking_eyes_open"

        frame = animation_dir / f"{self._avatar_character}_{requested_emotion}_{suffix}.png"
        if not frame.is_file():
            fallback = animation_dir / (
                f"{self._avatar_character}_{requested_emotion}_nottalking_eyes_open.png"
            )
            frame = fallback if fallback.is_file() else frame
        source = QUrl.fromLocalFile(str(frame)).toString() if frame.is_file() else ""
        if source != self._avatar_frame_source or requested_emotion != self._avatar_emotion:
            self._avatar_frame_source = source
            self._avatar_emotion = requested_emotion
            self.avatarChanged.emit()

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
        self._avatar_timer.stop()
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

    def _queue_remote_update(
        self,
        state: str,
        status: str,
        url: str = "",
        payload: Optional[dict] = None,
    ) -> None:
        self._remoteUpdateRequested.emit(state, status, url, payload or {})

    @Slot(str, str, str, object)
    def _apply_remote_update(
        self, state: str, status: str, url: str, payload: object
    ) -> None:
        self._remote_state = state
        self._remote_status = status
        self._remote_url = url
        data = payload if isinstance(payload, dict) else {}
        self._remote_error = str(data.get("error", ""))
        if "networks" in data:
            self._wifi_networks = list(data.get("networks") or [])
        self.remoteChanged.emit()

    @Slot(bool)
    def _apply_calibration_state(self, active: bool) -> None:
        if self._calibration_active == active:
            return
        self._calibration_active = active
        self.calibrationChanged.emit()

    @staticmethod
    def _remote_local_url() -> str:
        try:
            from modules.module_config import load_config
            from modules.module_wifi import WiFiManager

            port = int(load_config().get("ACCESS", {}).get("webui_port", 80))
            host = WiFiManager.HOTSPOT_IP
            return f"http://{host}:{port}" if port != 80 else f"http://{host}"
        except Exception:
            return "http://10.42.0.1"

    def _refresh_remote_worker(self) -> None:
        try:
            from modules.module_wifi import _get_manager

            status = _get_manager().get_status()
            mode = str(status.get("mode", "disconnected"))
            if mode == "hotspot":
                self._queue_remote_update(
                    "hotspot",
                    "TARS setup hotspot is active",
                    self._remote_local_url(),
                )
                return
            if mode == "client":
                try:
                    from modules.module_chatui import _get_tunnel_status

                    tunnel = _get_tunnel_status()
                    if tunnel.get("state") == "active" and tunnel.get("url"):
                        self._queue_remote_update(
                            "active", "Remote tunnel is online", str(tunnel["url"])
                        )
                        return
                except Exception:
                    pass
                ssid = str(status.get("ssid") or "Wi-Fi")
                self._queue_remote_update("ready", f"Connected to {ssid}")
                return
            self._queue_remote_update("offline", "No Wi-Fi connection")
        except Exception as exc:
            self._queue_remote_update(
                "error", "Unable to read remote-access status", "", {"error": str(exc)}
            )

    @Slot()
    def refreshRemoteAccess(self) -> None:
        self._queue_remote_update("checking", "Checking network and tunnel status")
        threading.Thread(
            target=self._refresh_remote_worker,
            name="QMLRemoteStatus",
            daemon=True,
        ).start()

    def _scan_wifi_worker(self) -> None:
        try:
            from modules.module_wifi import _get_manager

            networks = _get_manager().scan_networks(rescan=True)
            self._queue_remote_update(
                "networks",
                f"{len(networks)} network{'s' if len(networks) != 1 else ''} found",
                "",
                {"networks": networks},
            )
        except Exception as exc:
            self._queue_remote_update(
                "error", "Wi-Fi scan failed", "", {"error": str(exc)}
            )

    @Slot()
    def scanWifiNetworks(self) -> None:
        self._queue_remote_update("scanning", "Scanning for Wi-Fi networks")
        threading.Thread(
            target=self._scan_wifi_worker,
            name="QMLWiFiScan",
            daemon=True,
        ).start()

    def _connect_wifi_worker(self, ssid: str, password: str) -> None:
        try:
            from modules.module_wifi import _get_manager

            manager = _get_manager()
            if manager.get_status().get("mode") == "hotspot":
                manager.stop_hotspot()
            if manager.connect(ssid, password):
                self._queue_remote_update("ready", f"Connected to {ssid}")
            else:
                self._queue_remote_update(
                    "error",
                    f"Could not connect to {ssid}",
                    "",
                    {"error": "Check the password and try again."},
                )
        except Exception as exc:
            self._queue_remote_update(
                "error", f"Could not connect to {ssid}", "", {"error": str(exc)}
            )

    @Slot(str, str)
    def connectWifiNetwork(self, ssid: str, password: str) -> None:
        ssid = ssid.strip()
        if not ssid:
            self._apply_notice("SELECT A WI-FI NETWORK", 2400)
            return
        self._queue_remote_update("connecting", f"Connecting to {ssid}")
        threading.Thread(
            target=self._connect_wifi_worker,
            args=(ssid, password),
            name="QMLWiFiConnect",
            daemon=True,
        ).start()

    def _start_remote_worker(self) -> None:
        try:
            from modules.module_wifi import _get_manager

            manager = _get_manager()
            wifi_status = manager.get_status()
            if wifi_status.get("mode") != "client":
                self._queue_remote_update("starting", "Starting TARS setup hotspot")
                if not manager.start_hotspot():
                    raise RuntimeError("NetworkManager could not start the hotspot")
                self._queue_remote_update(
                    "hotspot",
                    "TARS setup hotspot is active",
                    self._remote_local_url(),
                )
                return

            from modules.module_chatui import (
                _cloudflared_bin,
                _get_tunnel_status,
                _install_cloudflared,
                _start_tunnel,
            )

            tunnel = _get_tunnel_status()
            if tunnel.get("state") == "active" and tunnel.get("url"):
                self._queue_remote_update(
                    "active", "Remote tunnel is online", str(tunnel["url"])
                )
                return
            if not _cloudflared_bin():
                self._queue_remote_update("starting", "Installing remote-access service")
                ok, error = _install_cloudflared()
                if not ok:
                    raise RuntimeError(str(error))
            self._queue_remote_update("starting", "Starting encrypted remote tunnel")
            ok, result = _start_tunnel()
            if not ok:
                raise RuntimeError(str(result))
            self._queue_remote_update("active", "Remote tunnel is online", str(result))
        except Exception as exc:
            self._queue_remote_update(
                "error", "Remote access failed", "", {"error": str(exc)}
            )

    @Slot()
    def startRemoteAccess(self) -> None:
        self._queue_remote_update("starting", "Preparing remote access")
        threading.Thread(
            target=self._start_remote_worker,
            name="QMLRemoteStart",
            daemon=True,
        ).start()

    def _stop_remote_worker(self, stop_hotspot: bool) -> None:
        try:
            if stop_hotspot:
                from modules.module_wifi import _get_manager

                _get_manager().stop_hotspot()
            else:
                from modules.module_chatui import _stop_tunnel

                _stop_tunnel()
            self._queue_remote_update("idle", "Remote access stopped")
        except Exception as exc:
            self._queue_remote_update(
                "error", "Unable to stop remote access", "", {"error": str(exc)}
            )

    @Slot()
    def stopRemoteAccess(self) -> None:
        stop_hotspot = self._remote_state == "hotspot"
        self._queue_remote_update("stopping", "Stopping remote access")
        threading.Thread(
            target=self._stop_remote_worker,
            args=(stop_hotspot,),
            name="QMLRemoteStop",
            daemon=True,
        ).start()

    @Slot(str)
    def launchApp(self, app_name: str) -> None:
        normalized = app_name.strip().upper()
        if normalized == "SERVO TEST":
            self.launchServoCalibration()
            return
        self._apply_notice(f"{normalized} APP IS NOT MIGRATED YET", 3200)

    def _servo_calibration_worker(self) -> None:
        handed_off = False
        return_code = None
        try:
            if self._begin_servo_calibration is None:
                raise RuntimeError("runtime calibration handoff is unavailable")

            ok, message = self._begin_servo_calibration()
            if not ok:
                raise RuntimeError(message)
            handed_off = True
            self._calibrationStateRequested.emit(True)
            self._noticeRequested.emit(
                "SERVO CALIBRATION ACTIVE · VOICE AND MOVEMENT PAUSED", 4200
            )

            script = self._base_dir / "app-servotester-qml.py"
            process = subprocess.Popen(
                [sys.executable, str(script), "--fullscreen"],
                cwd=self._base_dir,
            )
            with self._servo_process_lock:
                self._servo_tester_process = process
            return_code = process.wait()
        except Exception as exc:
            self._noticeRequested.emit(f"SERVO TESTER FAILED: {exc}", 5200)
        finally:
            restore_ok = True
            restore_message = "Servo calibration closed"
            if handed_off and self._end_servo_calibration is not None:
                try:
                    restore_ok, restore_message = self._end_servo_calibration()
                except Exception as exc:
                    restore_ok = False
                    restore_message = f"Servo restore failed: {exc}"

            with self._servo_process_lock:
                self._servo_tester_process = None
                self._calibration_launching = False
            self._calibrationStateRequested.emit(False)

            if handed_off:
                if return_code not in (None, 0):
                    self._noticeRequested.emit(
                        f"SERVO TESTER CLOSED WITH ERROR {return_code} · {restore_message}", 6000
                    )
                elif restore_ok:
                    self._noticeRequested.emit(restore_message.upper(), 4200)
                else:
                    self._noticeRequested.emit(restore_message.upper(), 6000)

    @Slot()
    def launchServoCalibration(self) -> None:
        with self._servo_process_lock:
            running = (
                self._servo_tester_process is not None
                and self._servo_tester_process.poll() is None
            )
            if self._calibration_launching or running:
                self._apply_notice("SERVO CALIBRATION IS ALREADY OPEN", 3200)
                return
            self._calibration_launching = True

        self._apply_notice("PREPARING SAFE SERVO HANDOFF", 3200)
        threading.Thread(
            target=self._servo_calibration_worker,
            name="QMLServoCalibration",
            daemon=True,
        ).start()

    @Slot()
    def exitProgram(self) -> None:
        self._apply_notice("STOPPING TARS", 5000)
        if self._request_stop:
            self._request_stop()
        else:
            self.runtimeStopped.emit()

    @Slot()
    def requestRestart(self) -> None:
        self._apply_notice("RESTARTING TARS", 5000)
        if self._request_restart:
            self._request_restart()
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

