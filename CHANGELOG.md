# Changelog

All notable TARS-AI V2 changes are recorded here. This project uses release
candidates for hardware validation before a final stable release.

## [Unreleased]

- Rebuilt the fast backward step as an exact directional mirror of the
  field-proven fast forward gait, unified normal backward command routing, and
  synchronized the servo-tester diagnostic replay with the production movement.

## [2.0.0-rc1] - Pending Raspberry Pi hardware certification

The code and documentation for this candidate are prepared, but the tag must not
be created until `Documentation/release-checklist-v2.0.0-rc1.txt` passes on the
physical TARS robot.

### Added

- PySide6/QML main interface with rotated on-device layout, live speech waveform,
  state display, camera preview, responsive text panels, and application/menu
  navigation.
- QML servo calibration interface with continuous sliders, hardware/mock modes,
  saved offsets, motion presets, diagnostics, and controlled ownership handoff.
- Dashboard, System Health, Audio Timeline, Eyes, Avatar, Clock, settings, loading,
  error, empty, and disabled-state components.
- Modern local WebUI for status, configuration, camera, and supervised movement.
- GPT Live transcription with local STT fallback and explicit device selection.
- Shared camera/vision pipeline, performance instrumentation, typed configuration,
  atomic writes, and release-focused failure handling.
- Fake-hardware coverage for servos, camera, microphone, network, configuration,
  QML loading/layouts, calibration persistence, launchers, and clean installation.
- Installation, audio, camera, servo safety, configuration, backup, troubleshooting,
  WebUI, upgrade/rollback, known-limitations, and release-checklist documentation.

### Changed

- Replaced the active Pygame presentation with PySide6/QML; Pygame sources remain
  archived for history and are not referenced by production launchers.
- Split large STT, QML, WebUI, servo, and servo-tester responsibilities behind
  testable controller/import boundaries.
- Centralized audio/TTS text sanitation and improved contraction pronunciation.
- Serialized movement ownership, cancellation, neutral recovery, watchdog behavior,
  and post-routine release so later voice/WebUI movements can run reliably.
- Preserved calibrated movement behavior while adding safer cancellation and
  neutral-return handling for expressive routines.
- Added explicit ReSpeaker input/original USB sound-card output configuration by
  stable device-name fragments.

### Fixed

- Duplicate movement acknowledgements, stale servo ownership, incomplete handshake
  and monster neutral returns, intermittent movement initialization, and unsafe
  follow-on movement after cancellation.
- Camera preview orientation, camera/vision ownership, and image-aware request paths.
- Oversized controls/text, inconsistent mute width, incorrect menu back navigation,
  and small/fullscreen layout regressions.
- LLM timeout/concurrency handling, repeated feature resource cleanup, and QML
  servo-tester dependency loading on Raspberry Pi.

### Security

- Disabled/redesigned unrestricted `sandbox_exec` behavior to remove an avoidable
  command-execution risk.
- Added typed configuration validation and atomic persistence to reduce malformed
  or partially written configuration.
- Documented that WebUI password sessions are intended for a trusted private LAN;
  local HTTP must not be exposed directly to the internet.

### Known limitations

- Physical servo safety, gait stability, audio routing, camera ribbons, thermals,
  and touch behavior require Raspberry Pi/TARS hardware certification.
- Cloud features depend on provider availability, credentials, account limits, and
  current model identifiers.
- See `Documentation/known-limitations.txt` for the full operating boundary.

