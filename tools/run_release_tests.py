#!/usr/bin/env python3
"""Run the hardware-free TARS release suite with optional strict gating."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
STRICT_DEPENDENCIES = {
    "PySide6": "PySide6",
    "NumPy": "numpy",
    "Requests": "requests",
    "Flask": "flask",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TARS-AI-v2 release tests")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="require all release dependencies and reject skipped tests",
    )
    parser.add_argument(
        "--pattern",
        default="test*.py",
        help="unittest discovery pattern (default: test*.py)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sys.path[:0] = [str(SRC), str(TESTS)]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    missing = [
        label
        for label, module in STRICT_DEPENDENCIES.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        message = "Missing release-test dependencies: " + ", ".join(missing)
        if args.strict:
            print(message, file=sys.stderr)
            print(
                f"Install them with: {sys.executable} -m pip install "
                "-r requirements-release-tests.txt",
                file=sys.stderr,
            )
            return 2
        print("NOTE: " + message + "; dependency-specific tests may be skipped.")

    suite = unittest.defaultTestLoader.discover(str(TESTS), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if args.strict and result.skipped:
        print("Strict release run rejected skipped tests:", file=sys.stderr)
        for test, reason in result.skipped:
            print(f"  {test}: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
