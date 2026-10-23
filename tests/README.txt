TARS-AI-v2 test suite
=====================

The servo tests use an in-memory PCA9685 and I2C implementation. They never
open GPIO, I2C, audio, camera, network, or physical servo hardware.

From the repository root on Linux or Raspberry Pi OS:

    PYTHONPATH=src:tests python -m unittest discover -s tests -v

On PowerShell:

    $env:PYTHONPATH = "src;tests"
    python -m unittest discover -s tests -v

The fake backend records every channel write and can inject probe or PWM
failures. The suite verifies controller retry/recovery, calibrated endpoint
mapping, safe pulse bounds, startup/shutdown behavior, calibration handoff,
movement serialization, cancellation, and both original forward-step profiles.

These tests validate software behavior only. They cannot prove that a gait is
mechanically stable or that physical calibration endpoints are safe for a
particular TARS build.
