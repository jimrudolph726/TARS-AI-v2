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
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

from modules.module_config import load_config  # noqa: E402
from modules.module_messageQue import queue_message  # noqa: E402


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
    from modules.module_ui_qml import TarsUIController

    controller = TarsUIController(BASE_DIR)
    runtime = TarsRuntime(config=config, ui_controller=controller, debug_mode=debug_mode)
    controller.bind_runtime(runtime.request_stop, runtime.request_shutdown)
    controller.runtimeStopped.connect(app.quit)

    engine = None
    if show_ui:
        engine = QQmlApplicationEngine()
        context = engine.rootContext()
        context.setContextProperty("controller", controller)
        context.setContextProperty("displayRotation", config["UI"].get("rotation", 0))
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
    app.aboutToQuit.connect(runtime.request_stop)
    app.aboutToQuit.connect(controller.stop)

    runtime.start()
    exit_code = app.exec()

    runtime.request_stop()
    runtime.join(timeout=10)
    controller.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
