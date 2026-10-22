"""TARS-AI V2 entry point.

PySide6 owns the process main thread and QML owns presentation. The robot
services run in ``TarsRuntime`` so model and hardware initialization never
freezes the touchscreen.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))
# Every QML control in the TARS interface has an explicit custom skin. The
# Basic style supports that consistently on Windows, VNC, and Raspberry Pi OS.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from modules.module_config import load_config  # noqa: E402
from modules.module_messageQue import queue_message  # noqa: E402


def _acquire_single_instance_lock():
    """Prevent two V2 runtimes from writing to the same I2C controller."""
    if os.name != "posix":
        return None

    import fcntl

    lock_path = Path(tempfile.gettempdir()) / "tars-ai-v2.lock"
    lock_handle = lock_path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + 12.0
    while True:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            # A just-closed UI can spend up to ten seconds joining its runtime
            # and releasing I2C. Let that cleanup finish before refusing a
            # genuine second instance.
            if time.monotonic() < deadline:
                time.sleep(0.25)
                continue

            lock_handle.seek(0)
            owner_pid = lock_handle.read().strip() or "unknown"
            message = (
                f"ERROR: TARS-AI V2 is already running (PID {owner_pid}). "
                "Close the existing interface before starting another copy."
            )
            print(message, file=sys.stderr, flush=True)
            queue_message(message)
            lock_handle.close()
            return False

    os.set_inheritable(lock_handle.fileno(), False)
    lock_handle.seek(0)
    lock_handle.truncate()
    lock_handle.write(str(os.getpid()))
    lock_handle.flush()
    return lock_handle


def _parse_runtime_options() -> tuple[bool, bool]:
    """Parse the legacy ``key=value`` launcher options."""
    show_ui = True
    debug_mode = False
    for arg in sys.argv[1:]:
        if "=" not in arg:
            continue
        key, value = arg.split("=", 1)
        enabled = value.lower() in ("1", "true", "yes", "on")
        if key == "show_ui":
            show_ui = enabled
        elif key == "speed":
            import modules.module_speed as speed

            speed.enabled = enabled
            if enabled:
                queue_message("LOAD: Speed profiling enabled")
        elif key == "debug" and enabled:
            debug_mode = True
    return show_ui, debug_mode


def _configure_logging(config: dict, debug_mode: bool) -> None:
    if debug_mode:
        config["debug_mode"] = True
        logging.basicConfig(level=logging.DEBUG, force=True)
        for name in (
            "picamera2",
            "libcamera",
            "piper_phonemize",
            "urllib3",
            "huggingface_hub",
            "sentence_transformers",
            "flashrank",
            "rustls",
            "h2",
            "hyper_util",
            "reqwest",
            "primp",
            "cookie_store",
            "asyncio",
        ):
            logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger("piper").setLevel(logging.INFO)
        queue_message("LOAD: Debug mode enabled")
    else:
        logging.basicConfig(level=logging.WARNING)
    logging.getLogger("bm25s").setLevel(logging.WARNING)


def _load_font(filename: str, fallback: str) -> str:
    from PySide6.QtGui import QFontDatabase

    font_path = BASE_DIR / "modules" / "UI" / filename
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    return families[0] if families else fallback


def main() -> int:
    # Keep this handle alive for the entire runtime. POSIX flock is released
    # automatically if the process exits or crashes, so stale lock files do
    # not block a later launch.
    instance_lock = _acquire_single_instance_lock()
    if instance_lock is False:
        return 3

    try:
        from PySide6.QtCore import QCoreApplication, QTimer, QUrl, Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:
        print("PySide6 is required for TARS-AI V2. Install requirements-main-ui-qml.txt.")
        print(f"Import error: {exc}")
        return 2

    config = load_config()
    show_ui_arg, debug_mode = _parse_runtime_options()
    show_ui = show_ui_arg and config["UI"].get("UI_enabled", True)
    _configure_logging(config, debug_mode)

    device_info = config.get("_device", {})
    raspberry_version = device_info.get("raspberry_version", "pi5")
    queue_message(f"LOAD: TARS-AI V2 starting on {raspberry_version.upper()}")
    queue_message(f"LOAD: Script running from: {BASE_DIR}")

    app = QGuiApplication(sys.argv) if show_ui else QCoreApplication(sys.argv)
    app.setApplicationName("TARS-AI")
    app.setOrganizationName("TARS-AI Community")

    from modules.module_runtime import TarsRuntime
    from modules.module_ui_qml import CameraImageProvider, TarsUIController

    controller = TarsUIController(BASE_DIR)
    runtime = TarsRuntime(config=config, ui_controller=controller, debug_mode=debug_mode)
    controller.bind_runtime(
        runtime.request_stop,
        runtime.request_restart,
        runtime.request_shutdown,
        runtime.begin_servo_calibration,
        runtime.end_servo_calibration,
    )
    controller.runtimeStopped.connect(app.quit)

    engine = None
    if show_ui:
        engine = QQmlApplicationEngine()
        engine.warnings.connect(
            lambda warnings: [
                print(f"QML: {warning.toString()}", file=sys.stderr)
                for warning in warnings
            ]
        )
        engine.addImageProvider("camera", CameraImageProvider(controller))
        context = engine.rootContext()
        context.setContextProperty("controller", controller)
        # TARS's display is physically mounted in portrait orientation relative
        # to the Pi framebuffer, so the complete logical UI is rotated right.
        context.setContextProperty("displayRotation", 90)
        context.setContextProperty(
            "initialWindowWidth", max(320, config["UI"].get("screen_width", 480))
        )
        context.setContextProperty(
            "initialWindowHeight", max(320, config["UI"].get("screen_height", 720))
        )
        context.setContextProperty("displayFontFamily", _load_font("pixelmix.ttf", "Sans Serif"))
        context.setContextProperty("monoFontFamily", _load_font("mono.ttf", "Monospace"))

        qml_path = BASE_DIR / "qml" / "main" / "TarsMain.qml"
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            print(f"Unable to load QML interface: {qml_path}")
            controller.stop()
            return 2

        window = engine.rootObjects()[0]
        if config["UI"].get("fullscreen", True):
            window.showFullScreen()
        if not config["UI"].get("show_mouse", False):
            QGuiApplication.setOverrideCursor(Qt.BlankCursor)
    else:
        queue_message("LOAD: Running with the Qt UI disabled")

    # A small timer lets Python service SIGINT while Qt is otherwise idle.
    signal_timer = QTimer()
    signal_timer.setInterval(250)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start()

    def request_stop(*_args) -> None:
        runtime.request_stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    # Do not connect aboutToQuit back into runtimeStopped -> app.quit.  If the
    # runtime finishes between emitting runtimeStopped and Qt processing that
    # signal, request_stop() sees a dead thread and emits runtimeStopped again,
    # creating a recursive quit loop. Cleanup runs immediately after exec().

    runtime.start()
    exit_code = app.exec()

    runtime.request_stop()
    runtime.join(timeout=10)
    controller.stop()
    if runtime.restart_requested:
        queue_message("SYSTEM: Restarting TARS-AI V2")
        try:
            os.execv(
                sys.executable,
                [sys.executable, str(BASE_DIR / "app.py"), *sys.argv[1:]],
            )
        except OSError as exc:
            queue_message(f"ERROR: Unable to restart TARS-AI V2: {exc}")
            return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
