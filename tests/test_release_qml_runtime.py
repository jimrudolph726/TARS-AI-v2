"""Headless QML loading and screenshot release checks.

These tests use the hardware-safe prototype controller and never start the
camera, microphone, network, LLM, or servo stack.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "src" / "app-main-qml.py"
HAS_PYSIDE = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(
    HAS_PYSIDE,
    "PySide6 is required for runtime QML checks; install requirements-release-tests.txt",
)
class QmlRuntimeReleaseTests(unittest.TestCase):
    def _render(self, width: int, height: int, *arguments: str) -> None:
        from PySide6.QtGui import QImage

        with tempfile.TemporaryDirectory(prefix="tars-qml-release-") as directory:
            screenshot = Path(directory) / "surface.png"
            env = os.environ.copy()
            env["QT_QPA_PLATFORM"] = "offscreen"
            env["QT_QUICK_BACKEND"] = "software"
            env["QT_QUICK_CONTROLS_STYLE"] = "Basic"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            command = [
                sys.executable,
                str(PROTOTYPE),
                "--rotation",
                "90",
                "--width",
                str(width),
                "--height",
                str(height),
                "--screenshot",
                str(screenshot),
                *arguments,
            ]
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            output = result.stdout + result.stderr
            self.assertEqual(0, result.returncode, output)
            self.assertTrue(screenshot.is_file(), output)

            lowered = output.casefold()
            for fatal in (
                "failed to load component",
                "is not a type",
                "typeerror:",
                "referenceerror:",
            ):
                self.assertNotIn(fatal, lowered, output)

            image = QImage(str(screenshot))
            self.assertFalse(image.isNull(), output)
            self.assertEqual((width, height), (image.width(), image.height()))

            # A successfully allocated but unpainted offscreen window can still
            # produce a valid PNG. Sample the image to ensure the interface was
            # actually rendered with multiple colors and its red accent.
            colors = set()
            red_accent = False
            x_step = max(1, width // 24)
            y_step = max(1, height // 24)
            for x in range(0, width, x_step):
                for y in range(0, height, y_step):
                    color = image.pixelColor(x, y)
                    colors.add((color.red(), color.green(), color.blue()))
                    red_accent = red_accent or (
                        color.red() > 110
                        and color.red() > color.green() * 1.4
                        and color.red() > color.blue() * 1.2
                    )
            self.assertGreater(len(colors), 6)
            self.assertTrue(red_accent)

    def test_registered_app_components_load(self):
        for app_id in (
            "clock",
            "dashboard",
            "system-health",
            "eyes",
            "avatar",
            "remote",
            "audio",
        ):
            with self.subTest(app=app_id):
                self._render(480, 720, "--app", app_id)

    def test_important_display_sizes_render(self):
        cases = (
            (480, 720, ()),
            (480, 800, ("--panel", "apps")),
            (800, 480, ("--panel", "menu")),
            (1080, 1920, ("--app", "system-health")),
        )
        for width, height, arguments in cases:
            with self.subTest(size=f"{width}x{height}", arguments=arguments):
                self._render(width, height, *arguments)


if __name__ == "__main__":
    unittest.main()
