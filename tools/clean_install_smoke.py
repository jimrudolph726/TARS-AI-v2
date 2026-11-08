#!/usr/bin/env python3
"""Offline smoke check for a freshly cloned TARS-AI-v2 checkout.

The check deliberately does not install packages or touch real hardware.  It
verifies that tracked templates can bootstrap runtime files, active Python is
syntactically valid, QML entry assets are present, and the safe prototype
entry point can expose its command line before a full runtime is configured.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from modules.module_config_store import validate_typed_config_file  # noqa: E402


def _require(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"Required clean-install file is missing: {path.relative_to(ROOT)}")


def main() -> int:
    required = (
        ROOT / ".env.template",
        ROOT / "requirements-main-ui-qml.txt",
        ROOT / "requirements-servotester-qml.txt",
        ROOT / "requirements-release-tests.txt",
        ROOT / "tars-launcher.sh",
        SRC / "app.py",
        SRC / "app-main-qml.py",
        SRC / "app-servotester-qml.py",
        SRC / "config.ini.template",
        SRC / "qml" / "main" / "TarsMain.qml",
        SRC / "qml" / "ServoCalibration.qml",
        SRC / "qml" / "fonts" / "pixelmix.ttf",
        SRC / "qml" / "fonts" / "mono.ttf",
    )
    for path in required:
        _require(path)

    for path in SRC.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    with tempfile.TemporaryDirectory(prefix="tars-clean-install-") as directory:
        clean_root = Path(directory)
        config_path = clean_root / "config.ini"
        env_path = clean_root / ".env"
        shutil.copy2(SRC / "config.ini.template", config_path)
        shutil.copy2(ROOT / ".env.template", env_path)
        validate_typed_config_file(config_path)
        if not env_path.read_text(encoding="utf-8").strip():
            raise RuntimeError(".env.template is empty")

    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(SRC / "app-main-qml.py"), "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0 or "--screenshot" not in result.stdout:
        raise RuntimeError(
            "QML prototype CLI smoke failed:\n" + result.stdout + result.stderr
        )

    print("CLEAN INSTALL SMOKE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
