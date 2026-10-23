"""Tests for secure default skill enablement and persistence."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import module_skills


class SkillDefaultTests(unittest.TestCase):
    def _manager(self):
        manager = module_skills.SkillManager()
        manager._skills = {"sandbox_exec": object(), "calculator": object()}
        manager._skill_meta = {
            "sandbox_exec": {"enabled_by_default": False},
            "calculator": {},
        }
        return manager

    def test_secure_default_is_applied_without_config_section(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.ini"
            config_path.write_text("", encoding="utf-8")
            manager = self._manager()
            with patch.object(
                module_skills, "_get_config_path", return_value=str(config_path)
            ):
                manager._load_config()

            self.assertFalse(manager.is_enabled("sandbox_exec"))
            self.assertTrue(manager.is_enabled("calculator"))

    def test_explicit_opt_in_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.ini"
            config_path.write_text("", encoding="utf-8")
            manager = self._manager()
            with patch.object(
                module_skills, "_get_config_path", return_value=str(config_path)
            ):
                manager._load_config()
                manager.set_enabled("sandbox_exec", True)
                manager._load_config()

            self.assertTrue(manager.is_enabled("sandbox_exec"))
            self.assertIn("disabled = false", config_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
