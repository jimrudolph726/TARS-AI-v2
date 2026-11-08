"""Static contracts for the responsive QML visual system.

The tests intentionally avoid importing Qt so they run on development hosts
and in fake-hardware CI. Runtime rendering is still verified on the Pi, while
these checks prevent accidental removal of scale caps and touch baselines.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "src" / "qml" / "main"
TOKENS = QML / "components" / "UiTokens.js"


def _token_number(name: str) -> float:
    text = TOKENS.read_text(encoding="utf-8")
    match = re.search(rf"^var\s+{re.escape(name)}\s*=\s*([0-9.]+)\s*$", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"Missing numeric UI token: {name}")
    return float(match.group(1))


class QmlVisualSystemTests(unittest.TestCase):
    def test_scale_is_bounded_for_native_small_and_fullscreen_surfaces(self):
        reference_width = _token_number("canvasWidth")
        reference_height = _token_number("canvasHeight")
        maximum = _token_number("maximumUiScale")

        def scale(width: int, height: int) -> float:
            return max(0.66, min(width / reference_width, height / reference_height, maximum))

        self.assertAlmostEqual(1.0, scale(480, 720))
        self.assertAlmostEqual(1.0, scale(480, 800))  # native rotated fullscreen
        self.assertAlmostEqual(2 / 3, scale(800, 480))  # rotated windowed development
        self.assertAlmostEqual(2 / 3, scale(320, 480))
        self.assertEqual(maximum, scale(1080, 1920))
        self.assertEqual(maximum, scale(1340, 2510))  # high-resolution VNC
        self.assertEqual(maximum, scale(1440, 2560))

    def test_touch_target_never_shrinks_below_baseline(self):
        touch_min = _token_number("touchMin")
        content_max = _token_number("maximumContentScale")

        for ui_scale in (0.66, 0.78, 1.0, 1.25, 1.45):
            content_scale = max(0.78, min(ui_scale, content_max))
            control_scale = max(0.82, content_scale)
            target = max(touch_min, touch_min * control_scale)
            self.assertGreaterEqual(target, 44)
            self.assertLessEqual(target, 55)

    def test_main_window_uses_scale_caps_and_bounded_modals(self):
        text = (QML / "TarsMain.qml").read_text(encoding="utf-8")
        self.assertIn("Ui.clampedScale(width, height)", text)
        self.assertIn("readonly property real touchTarget", text)
        self.assertIn("width: Math.min(parent.width - 2 * scene.modalMargin", text)
        self.assertIn("Math.min(parent.height - 2 * scene.modalMargin", text)

    def test_reusable_controls_use_shared_visual_tokens(self):
        components = QML / "components"
        for name in (
            "TarsButton.qml",
            "TarsPanel.qml",
            "TarsSlider.qml",
            "StatusCard.qml",
            "SettingsRow.qml",
            "ConversationCard.qml",
        ):
            text = (components / name).read_text(encoding="utf-8")
            self.assertIn('import "UiTokens.js" as Ui', text, name)

        button = (components / "TarsButton.qml").read_text(encoding="utf-8")
        slider = (components / "TarsSlider.qml").read_text(encoding="utf-8")
        self.assertIn("implicitHeight: Math.max(Ui.touchMin", button)
        self.assertIn("implicitHeight: Math.max(Ui.touchMin", slider)

    def test_interactive_apps_keep_explicit_touch_targets(self):
        dashboard = (QML / "DashboardApp.qml").read_text(encoding="utf-8")
        remote = (QML / "RemoteApp.qml").read_text(encoding="utf-8")
        health = (QML / "SystemHealthApp.qml").read_text(encoding="utf-8")

        self.assertIn("Math.max(Ui.touchMin", dashboard)
        self.assertIn("readonly property real touchTarget", remote)
        self.assertIn("readonly property real touchTarget", health)
        self.assertIn("columns: root.compactWidth ? 2 : 4", health)


if __name__ == "__main__":
    unittest.main()

