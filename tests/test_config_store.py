import configparser
import io
import tempfile
import threading
import time
import unittest
from pathlib import Path

from modules.module_config_store import (
    ConfigValidationError,
    atomic_update_text,
    atomic_write_text,
    load_typed_config,
    validate_ini_file,
    validate_typed_config_file,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "config.ini.template"


class ConfigStoreTests(unittest.TestCase):
    def _copy_template(self, directory: str) -> Path:
        target = Path(directory) / "config.ini"
        target.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        return target

    def test_template_loads_into_typed_snapshot(self):
        config = load_typed_config(TEMPLATE)
        self.assertIsInstance(config.servo.left_main_min, int)
        self.assertIsInstance(config.stt.speaker_id_enabled, bool)
        self.assertEqual(config.ui.rotation, 90)
        self.assertEqual(config.servo.legacy_dict()["leftMainMin"], 550)
        self.assertTrue(config.servo.movement_watchdog_enabled)
        self.assertEqual(config.servo.movement_watchdog_timeout, 45.0)
        self.assertEqual(config.servo.movement_stall_timeout, 8.0)
        with self.assertRaises(TypeError):
            config.sections["SERVO"]["leftmainmin"] = "10"

    def test_watchdog_limits_reject_unsafe_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self._copy_template(directory)
            text = target.read_text(encoding="utf-8")
            text = text.replace(
                "movement_watchdog_timeout = 45",
                "movement_watchdog_timeout = 4",
            )
            text = text.replace(
                "movement_stall_timeout = 8",
                "movement_stall_timeout = 2",
            )
            target.write_text(text, encoding="utf-8")

            with self.assertRaises(ConfigValidationError) as raised:
                load_typed_config(target)

            message = str(raised.exception)
            self.assertIn("movement_watchdog_timeout must be at least 10", message)
            self.assertIn("movement_stall_timeout must be at least 6", message)

    def test_invalid_boolean_and_rotation_are_reported_together(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self._copy_template(directory)
            text = target.read_text(encoding="utf-8")
            text = text.replace("use_indicators = True", "use_indicators = perhaps")
            text = text.replace("\nrotation = 90\n", "\nrotation = 45\n")
            target.write_text(text, encoding="utf-8")

            with self.assertRaises(ConfigValidationError) as raised:
                load_typed_config(target)

            message = str(raised.exception)
            self.assertIn("[STT] use_indicators must be true or false", message)
            self.assertIn("[UI] rotation must be one of", message)

    def test_offset_that_pushes_servo_out_of_range_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self._copy_template(directory)
            text = target.read_text(encoding="utf-8").replace(
                "leftMainOffset = 0", "leftMainOffset = 100"
            )
            target.write_text(text, encoding="utf-8")

            with self.assertRaises(ConfigValidationError) as raised:
                load_typed_config(target)

            self.assertIn("resolves to unsafe PWM value 650", str(raised.exception))

    def test_failed_validation_never_replaces_original(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self._copy_template(directory)
            original = target.read_text(encoding="utf-8")
            invalid = original.replace("\nrotation = 90\n", "\nrotation = 13\n")

            with self.assertRaises(ConfigValidationError):
                atomic_write_text(
                    target,
                    invalid,
                    validator=validate_typed_config_file,
                    create_backup=False,
                )

            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertEqual(list(Path(directory).glob(".config.ini.*.tmp")), [])

    def test_valid_atomic_write_creates_backup_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self._copy_template(directory)
            original = target.read_text(encoding="utf-8")
            updated = original.replace("webui_port = 80", "webui_port = 8080")
            backup = Path(directory) / "config_backup.ini"

            atomic_write_text(
                target,
                updated,
                validator=validate_typed_config_file,
                backup_path=backup,
                keep_history=True,
            )

            self.assertIn("webui_port = 8080", target.read_text(encoding="utf-8"))
            self.assertEqual(backup.read_text(encoding="utf-8"), original)
            self.assertEqual(len(list((Path(directory) / "config_backups").glob("*.ini"))), 1)

    def test_concurrent_updates_do_not_lose_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "counter.ini"
            target.write_text("[COUNTER]\nvalue = 0\n", encoding="utf-8")
            errors = []

            def increment():
                try:
                    def transform(current):
                        parser = configparser.ConfigParser()
                        parser.read_string(current)
                        value = parser.getint("COUNTER", "value")
                        # Make a lost update likely if read/modify/write is not locked.
                        time.sleep(0.003)
                        parser.set("COUNTER", "value", str(value + 1))
                        rendered = io.StringIO()
                        parser.write(rendered)
                        return rendered.getvalue()

                    atomic_update_text(
                        target,
                        transform,
                        validator=validate_ini_file,
                        create_backup=False,
                    )
                except Exception as exc:  # pragma: no cover - assertion reports detail
                    errors.append(exc)

            threads = [threading.Thread(target=increment) for _ in range(12)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            parser = configparser.ConfigParser()
            parser.read(target)
            self.assertEqual(parser.getint("COUNTER", "value"), 12)


if __name__ == "__main__":
    unittest.main()
