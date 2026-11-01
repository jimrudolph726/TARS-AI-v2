"""Tests for presentation-toolkit-neutral UI bridge services."""

from __future__ import annotations

import unittest

from modules.module_display import (
    present_image,
    register_image_presenter,
    unregister_image_presenter,
)
from modules.module_expression_state import Mood, get_mood, set_mood


class UIServiceTests(unittest.TestCase):
    def tearDown(self):
        set_mood(Mood.NEUTRAL)

    def test_expression_state_accepts_enum_and_name(self):
        self.assertEqual(Mood.CURIOUS, set_mood("curious"))
        self.assertEqual(Mood.CURIOUS, get_mood())
        self.assertEqual(Mood.HAPPY, set_mood(Mood.HAPPY))

    def test_expression_state_rejects_unknown_mood(self):
        with self.assertRaises(KeyError):
            set_mood("not-a-mood")

    def test_display_bridge_registers_and_releases_presenter(self):
        calls = []

        def presenter(path, duration):
            calls.append((path, duration))

        self.assertFalse(present_image("before.png"))
        register_image_presenter(presenter)
        self.assertTrue(present_image("image.png", duration=12))
        self.assertEqual([("image.png", 12)], calls)
        unregister_image_presenter(presenter)
        self.assertFalse(present_image("after.png"))


if __name__ == "__main__":
    unittest.main()
