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

The LLM transport tests use fake HTTP sessions and never contact an AI service.
They verify network deadlines, bounded retries, permanent-error handling,
partial-stream duplicate prevention, response cleanup, and cancellation of
outdated preemptive voice requests.

The WebUI boundary tests parse the active Python modules without starting the
Flask server. They prevent Pygame from leaking back into the Qt/QML or browser
interfaces, verify that importing the WebUI package starts no threads or servo
hardware, and preserve the browser route contract during module extraction.

These tests validate software behavior only. They cannot prove that a gait is
mechanically stable or that physical calibration endpoints are safe for a
particular TARS build.
