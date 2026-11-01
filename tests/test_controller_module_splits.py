"""Unit and architecture tests for extracted controller services.

These tests intentionally avoid Qt, audio devices, I2C, and the network.  They
exercise the pure rules that were formerly embedded in the large STT, QML,
servo, and servo-tester controllers and lock in the new import boundaries.
"""

from __future__ import annotations

import ast
import struct
import unittest
import wave
from pathlib import Path

import numpy as np

from modules.module_servo_math import (
    channel_bounds,
    eased_progress,
    percentage_to_value,
    pulse_to_duty_cycle,
    synchronized_duration,
    validate_write,
)
from modules.module_servo_tester_model import (
    SERVO_DEFINITIONS,
    ServoCalibrationModel,
)
from modules.module_stt_audio import STTAudioProcessor
from modules.module_stt_bargein import find_novel_words, normalize_words
from modules.module_stt_wake import fuzzy_wake_word_match
from modules.module_ui_remote import RemoteAccessService
from modules.module_ui_telemetry import format_uptime


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _import_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _servo_config() -> dict[str, str]:
    config = {"arms_present": "True"}
    for definition in SERVO_DEFINITIONS.values():
        config[definition["config"]] = "0"
        first, second = definition["limits"]
        config.setdefault(first, "100")
        config.setdefault(second, "500")
    return config


class STTServiceTests(unittest.TestCase):
    def test_audio_processor_handles_gain_rms_and_clipping(self):
        processor = STTAudioProcessor(amp_gain=2.0)
        samples = np.array([[-20000], [1000], [20000]], dtype=np.int16)

        self.assertAlmostEqual(
            processor.compute_amplified_rms(samples),
            processor.compute_rms(samples) * 2.0,
        )
        self.assertEqual([-32768, 2000, 32767], processor.amplify(samples).flatten().tolist())
        self.assertIsNone(processor.compute_rms(np.zeros(4, dtype=np.int16)))

    def test_audio_processor_builds_valid_wav_and_float_audio(self):
        chunks = [np.array([0, 16384], dtype=np.int16), np.array([-16384], dtype=np.int16)]
        buffer = STTAudioProcessor.chunks_to_wav_buffer(chunks, 16000)
        with wave.open(buffer, "rb") as wav_file:
            self.assertEqual(1, wav_file.getnchannels())
            self.assertEqual(16000, wav_file.getframerate())
            self.assertEqual(3, wav_file.getnframes())
            self.assertEqual((0, 16384, -16384), struct.unpack("<hhh", wav_file.readframes(3)))

        audio = STTAudioProcessor.chunks_to_float32(chunks)
        np.testing.assert_allclose([0.0, 0.5, -0.5], audio)

    def test_noise_floor_rejects_outlier_and_text_filter_rejects_artifacts(self):
        self.assertEqual(13.0, STTAudioProcessor.noise_floor([10, 11, 12, 13, 500]))
        self.assertFalse(STTAudioProcessor.meaningful_text("um"))
        self.assertFalse(STTAudioProcessor.meaningful_text("."))
        self.assertTrue(STTAudioProcessor.meaningful_text("move forward"))

    def test_wake_match_allows_small_transcription_errors(self):
        self.assertTrue(fuzzy_wake_word_match("please hay tars", "hey tars"))
        self.assertFalse(fuzzy_wake_word_match("good morning robot", "hey tars"))

    def test_bargein_filter_separates_tts_bleed_from_new_speech(self):
        tts_words = set(normalize_words("All systems are operational and ready."))
        self.assertEqual([], find_novel_words("systems operational ready", tts_words))
        self.assertEqual(["stop"], find_novel_words("systems stop", tts_words))


class ServoServiceTests(unittest.TestCase):
    def test_servo_math_preserves_envelopes_and_recovery_rule(self):
        ranges = {0: (220, 460)}
        self.assertEqual((220, 460), channel_bounds(0, ranges))
        self.assertEqual(((0, 220), None), validate_write(0, 220, (220, 460)))
        self.assertIsNotNone(validate_write(0, 219, (220, 460))[1])
        self.assertEqual(
            (0, 210),
            validate_write(0, 210, (220, 460), current_value=200)[0],
        )
        self.assertIsNotNone(validate_write(0, 190, (220, 460), current_value=200)[1])

    def test_servo_math_mapping_and_timing_are_bounded(self):
        self.assertEqual(1638, pulse_to_duty_cycle(0))
        self.assertEqual(100, percentage_to_value(1, 100, 500))
        self.assertEqual(500, percentage_to_value(100, 100, 500))
        self.assertIsNone(percentage_to_value(0, 100, 500))
        self.assertEqual(-1, percentage_to_value(-1, 100, 500, hold=True))
        self.assertEqual(0.0, eased_progress(-1.0, 1.0))
        self.assertEqual(1.0, eased_progress(2.0, 1.0))
        self.assertGreaterEqual(synchronized_duration(0, 1.0), 0.10)

    def test_calibration_model_clamps_offsets_and_maps_full_range(self):
        model = ServoCalibrationModel(_servo_config())
        self.assertTrue(model.arms_present())
        self.assertEqual((100, 500), model.effective_endpoints("left_height"))
        self.assertEqual(100, model.range_target_pulse("left_height", 0))
        self.assertEqual(500, model.range_target_pulse("left_height", 100))
        minimum, maximum = model.offset_bounds("left_height")
        self.assertTrue(model.offset_is_safe("left_height", minimum))
        self.assertTrue(model.offset_is_safe("left_height", maximum))
        self.assertFalse(model.offset_is_safe("left_height", maximum + 1))

    def test_calibration_config_update_and_revert_are_model_owned(self):
        config = _servo_config()
        model = ServoCalibrationModel(config)
        model.servos["left_height"]["value"] = 7
        model.accept_saved()
        model.servos["left_height"]["value"] = 9
        model.revert()
        self.assertEqual(7, model.servos["left_height"]["value"])

        lines = ["[SERVO]\n", "arms_present = True\n"]
        for definition in SERVO_DEFINITIONS.values():
            lines.append(f"{definition['config']} = 0\n")
        updated = model.update_config_text("".join(lines))
        self.assertIn("perfectLeftHeightOffset = 7", updated)


class QMLServiceTests(unittest.TestCase):
    def test_remote_service_publishes_transport_neutral_payload(self):
        updates = []
        service = RemoteAccessService(
            lambda state, status, url, payload: updates.append((state, status, url, payload))
        )
        service._send("ready", "Connected", "http://tars", ssid="TARS")
        self.assertEqual(
            [("ready", "Connected", "http://tars", {"ssid": "TARS"})],
            updates,
        )

    def test_uptime_formatting_is_presentation_ready(self):
        self.assertEqual("0m", format_uptime(0))
        self.assertEqual("2h 5m", format_uptime(7500))
        self.assertEqual("2d 1h", format_uptime(176400))


class ControllerBoundaryTests(unittest.TestCase):
    def test_pure_extractions_do_not_import_qt_or_hardware_drivers(self):
        pure_modules = [
            "module_stt_audio.py",
            "module_stt_bargein.py",
            "module_stt_wake.py",
            "module_ui_remote.py",
            "module_ui_telemetry.py",
            "module_servo_math.py",
            "module_servo_tester_model.py",
        ]
        forbidden = ("PySide6", "board", "busio", "adafruit_pca9685")
        offenders = {}
        for filename in pure_modules:
            imports = _import_names(SRC / "modules" / filename)
            bad = sorted(
                name for name in imports
                if any(name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden)
            )
            if bad:
                offenders[filename] = bad
        self.assertEqual({}, offenders)

    def test_facades_use_the_extracted_services(self):
        expected = {
            "module_stt.py": {
                "modules.module_stt_audio",
                "modules.module_stt_bargein",
                "modules.module_stt_wake",
            },
            "module_ui_qml.py": {
                "modules.module_ui_qml_models",
                "modules.module_ui_remote",
                "modules.module_ui_telemetry",
            },
            "module_servoctl.py": {
                "modules.module_servo_hardware",
                "modules.module_servo_math",
            },
        }
        for filename, required in expected.items():
            imports = _import_names(SRC / "modules" / filename)
            self.assertEqual(set(), required - imports, filename)

        tester_imports = _import_names(SRC / "app-servotester-qml.py")
        self.assertIn("modules.module_servo_tester_model", tester_imports)
        self.assertIn("modules.module_servo_tester_hardware", tester_imports)


if __name__ == "__main__":
    unittest.main()
