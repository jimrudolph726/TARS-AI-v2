"""Clean-checkout, launcher, import-boundary, and config release checks."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from modules.module_config_store import ConfigValidationError, load_typed_config


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TEMPLATE = SRC / "config.ini.template"


class CleanInstallSmokeTests(unittest.TestCase):
    def test_offline_clean_install_smoke(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "clean_install_smoke.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("CLEAN INSTALL SMOKE: PASS", result.stdout)

    def test_release_dependency_manifest_covers_strict_suite(self):
        manifest = (ROOT / "requirements-release-tests.txt").read_text(
            encoding="utf-8"
        ).casefold()
        for dependency in ("pyside6", "numpy", "requests", "flask"):
            self.assertIn(dependency, manifest)


class LauncherContractTests(unittest.TestCase):
    def test_launchers_target_only_active_qml_interfaces(self):
        launchers = (
            "Install.sh",
            "tars-launcher.sh",
            "run-main-ui-demo.sh",
            "run-main-ui-demo.bat",
            "run-servotester-demo.bat",
            "lp.sh",
            "toggle-autostart.sh",
            "launch_retropie.sh",
        )
        forbidden = (
            "pygame",
            "app-start.py",
            "app-servotester.py",
            "module_ui.py",
        )
        offenders = {}
        for name in launchers:
            text = (ROOT / name).read_text(encoding="utf-8").casefold()
            hits = [token for token in forbidden if token in text]
            if hits:
                offenders[name] = hits
        self.assertEqual({}, offenders)

        for name in ("run-main-ui-demo.sh", "run-main-ui-demo.bat"):
            self.assertIn(
                "app-main-qml.py",
                (ROOT / name).read_text(encoding="utf-8"),
            )
        self.assertIn(
            "app-servotester-qml.py",
            (ROOT / "run-servotester-demo.bat").read_text(encoding="utf-8"),
        )
        production_launcher = (ROOT / "tars-launcher.sh").read_text(encoding="utf-8")
        self.assertIn("src/app.py", production_launcher)

        production_entry = (SRC / "app.py").read_text(encoding="utf-8")
        self.assertIn("PySide6", production_entry)
        self.assertIn("modules.module_ui_qml", production_entry)
        self.assertNotIn("pygame", production_entry.casefold())

    def test_active_python_cannot_import_archived_interface(self):
        offenders = {}
        for path in SRC.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            names = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
            bad = [
                name for name in names
                if name == "pygame" or name.startswith("pygame.")
                or name == "legacy" or name.startswith("legacy.")
            ]
            if bad:
                offenders[str(path.relative_to(ROOT))] = bad
        self.assertEqual({}, offenders)


class ReleaseConfigValidationTests(unittest.TestCase):
    def test_release_critical_ranges_report_all_errors_together(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "config.ini"
            text = TEMPLATE.read_text(encoding="utf-8")
            replacements = {
                "mic_amp_gain": "-1",
                "camera_rotation": "45",
                "webui_port": "70000",
                "screen_width": "0",
            }
            for key, value in replacements.items():
                text, count = re.subn(
                    rf"(?m)^{re.escape(key)}\s*=.*$",
                    f"{key} = {value}",
                    text,
                )
                self.assertEqual(1, count, key)
            target.write_text(text, encoding="utf-8")

            with self.assertRaises(ConfigValidationError) as raised:
                load_typed_config(target)

            message = str(raised.exception)
            for expected in (
                "mic_amp_gain must be at least 0",
                "camera_rotation must be one of",
                "webui_port must be at most 65535",
                "screen_width must be at least 1",
            ):
                self.assertIn(expected, message)


if __name__ == "__main__":
    unittest.main()
