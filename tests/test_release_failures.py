"""Hardware-free failure injection for camera, microphone, and networking."""

from __future__ import annotations

import importlib.util
import io
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np  # Preload native extension before temporary sys.modules patches.

from modules.module_ui_remote import RemoteAccessService


ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "src" / "modules"
_NUMPY_PRELOAD = np


def _load_isolated(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CameraFailureTests(unittest.TestCase):
    def test_camera_initialization_failure_is_reported_without_a_thread(self):
        config_module = types.ModuleType("modules.module_config")
        config_module.load_config = lambda: {
            "UI": {"target_fps": 30},
            "VISION": {"camera_rotation": 90},
        }

        picamera_module = types.ModuleType("picamera2")

        class FailingPicamera:
            def __init__(self):
                raise RuntimeError("simulated camera disconnect")

        picamera_module.Picamera2 = FailingPicamera
        cv2_module = types.ModuleType("cv2")

        with patch.dict(
            sys.modules,
            {
                "modules.module_config": config_module,
                "picamera2": picamera_module,
                "cv2": cv2_module,
            },
        ):
            camera_module = _load_isolated(
                "_release_fake_camera", MODULES / "module_camera.py"
            )
            camera_module.CameraModule._instance = None
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                camera = camera_module.CameraModule(640, 480, use_camera_module=True)

        self.assertIsNone(camera.picam2)
        self.assertFalse(camera.running)
        self.assertIsNone(camera.thread)


class MicrophoneFailureTests(unittest.TestCase):
    def test_missing_microphone_falls_back_without_crashing_startup(self):
        config_module = types.ModuleType("modules.module_config")
        config_module.load_config = lambda: {"AUDIO": {"input_device": "ReSpeaker"}}

        sounddevice_module = types.ModuleType("sounddevice")
        sounddevice_module.default = types.SimpleNamespace(device=(-1, -1))
        sounddevice_module.query_devices = lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("simulated PortAudio failure")
        )
        sounddevice_module._terminate = lambda: None
        sounddevice_module._initialize = lambda: None

        soxr_module = types.ModuleType("soxr")
        soxr_module.resample = lambda data, _source, _target: data

        with patch.dict(
            sys.modules,
            {
                "modules.module_config": config_module,
                "sounddevice": sounddevice_module,
                "soxr": soxr_module,
            },
        ):
            mic_module = _load_isolated("_release_fake_mic", MODULES / "module_mic.py")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                device, rate = mic_module.get_device_info(retries=1, backoff=0)

        self.assertIsNone(device)
        self.assertEqual(16000, rate)


class NetworkFailureTests(unittest.TestCase):
    @staticmethod
    def _failing_wifi_module():
        module = types.ModuleType("modules.module_wifi")

        def fail():
            raise RuntimeError("simulated NetworkManager outage")

        module._get_manager = fail
        return module

    def test_remote_operations_publish_recoverable_error_states(self):
        updates = []
        service = RemoteAccessService(
            lambda state, status, url, payload: updates.append(
                {"state": state, "status": status, "url": url, **payload}
            )
        )

        with patch.dict(
            sys.modules,
            {"modules.module_wifi": self._failing_wifi_module()},
        ):
            operations = (
                service.refresh,
                service.scan_wifi,
                lambda: service.connect_wifi("TARS-NET", "secret"),
                service.start,
                lambda: service.stop(stop_hotspot=True),
            )
            for operation in operations:
                updates.clear()
                operation()
                self.assertEqual(1, len(updates))
                self.assertEqual("error", updates[0]["state"])
                self.assertIn("simulated NetworkManager outage", updates[0]["error"])


if __name__ == "__main__":
    unittest.main()
