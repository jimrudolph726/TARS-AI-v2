TARS-AI-v2 test suite
=====================

The servo tests use an in-memory PCA9685 and I2C implementation. They never
open GPIO, I2C, audio, camera, network, or physical servo hardware.

From the repository root on Linux or Raspberry Pi OS:

    PYTHONPATH=src:tests python -m unittest discover -s tests -v

On PowerShell:

    $env:PYTHONPATH = "src;tests"
    python -m unittest discover -s tests -v

Release gate
------------

The strict release gate installs no packages and never opens physical
hardware. Install its small, explicit dependency manifest once, then run:

    python -m pip install -r requirements-release-tests.txt
    python tools/run_release_tests.py --strict

On the Raspberry Pi, use the project interpreter:

    src/.venv/bin/python tools/run_release_tests.py --strict

Without --strict, missing desktop-only dependencies are reported and their
specific tests are skipped. Strict mode rejects missing dependencies and any
skipped test, which is the mode used by the GitHub Actions release workflow.

The release layer loads every registered QML application with the safe mock
controller, renders screenshots at 480x720, 480x800, 800x480, and 1080x1920,
and checks that each image is nonblank and contains the TARS accent palette.
Screenshots are written only to temporary directories. It also injects camera,
microphone, and NetworkManager failures; verifies calibration offsets after a
fresh config/model reload; audits active import and launcher boundaries; and
runs an offline clean-checkout smoke test.

The fake backend records every channel write and can inject probe or PWM
failures. The suite verifies controller retry/recovery, calibrated endpoint
mapping, safe pulse bounds, startup/shutdown behavior, calibration handoff,
movement serialization, cancellation, and both original forward-step profiles.
They also inject PCA9685 frequency resets before and during movement, verify
the legacy stepper cannot flood commands above its 50 Hz cadence, and confirm
that torque-free joints re-engage and settle before following a new target.

The LLM transport tests use fake HTTP sessions and never contact an AI service.
They verify network deadlines, bounded retries, permanent-error handling,
partial-stream duplicate prevention, response cleanup, and cancellation of
outdated preemptive voice requests.

The interface boundary tests parse every active Python module without starting
the Flask server. They prevent Pygame or archived UI imports from leaking back
under src/, verify the installer and launchers remain QML-only, confirm that
importing the WebUI package starts no threads or servo hardware, and preserve
the browser route contract during module extraction.

The controller-split tests exercise the pure STT audio, wake-word and barge-in
rules; servo conversion and calibration rules; QML telemetry and remote-access
services; and import boundaries between those services and their controller
facades. They do not create a Qt application, open an audio device, contact a
network service, or initialize servo hardware.

The offline clean-install check can also be run by itself:

    python tools/clean_install_smoke.py

These tests validate software behavior only. They cannot prove that a gait is
mechanically stable or that physical calibration endpoints are safe for a
particular TARS build.
