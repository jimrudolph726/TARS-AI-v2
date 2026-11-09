"""Static contracts for QML loading, error, empty, and recovery states.

These checks do not import Qt, so they can run on development hosts and in
fake-hardware CI. Rendering and touch behavior are still smoke-tested on the
Raspberry Pi.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "src" / "qml" / "main"
CONTROLLER = ROOT / "src" / "modules" / "module_ui_qml.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class QmlAppStateTests(unittest.TestCase):
    def test_shared_state_view_supports_recovery_actions(self):
        text = _read(QML / "components" / "AppStateView.qml")
        for contract in (
            'property string actionText: ""',
            'property bool actionEnabled: true',
            "signal actionTriggered()",
            "onClicked: root.actionTriggered()",
            "Math.max(Ui.touchMin",
        ):
            self.assertIn(contract, text)

    def test_main_interface_covers_empty_and_recoverable_surfaces(self):
        text = _read(QML / "TarsMain.qml")
        self.assertIn("conversationList.count === 0", text)
        self.assertIn('title: "NO CONVERSATION YET"', text)
        self.assertIn('actionText: controller.cameraError.length ? "RETRY CAMERA"', text)
        self.assertIn("function retryActiveApp()", text)
        self.assertIn('actionText: appLoader.status === Loader.Error ? "RETRY APP"', text)
        self.assertIn("readonly property bool runtimeFailed", text)
        controller = _read(CONTROLLER)
        self.assertIn(
            "self._runtime_ready = self._runtime_ready or ready", controller
        )

    def test_backward_diagnostic_is_production_matched_and_sequential(self):
        tester = _read(ROOT / "src" / "app-servotester-qml.py")
        calibration = _read(ROOT / "src" / "qml" / "ServoCalibration.qml")

        self.assertIn("body_swing_execution_phases", tester)
        self.assertIn("BACKWARD_DIAGNOSTIC_TIME_SCALE", tester)
        self.assertIn("self._diagnostic_phase + 1", tester)
        self.assertIn("move_legs_timed(*pose, duration=duration)", tester)
        self.assertIn("|| modelData.next", calibration)
        self.assertIn("P is production time", calibration)

    def test_data_apps_expose_meaningful_empty_and_error_states(self):
        dashboard = _read(QML / "DashboardApp.qml")
        health = _read(QML / "SystemHealthApp.qml")
        remote = _read(QML / "RemoteApp.qml")

        self.assertIn('actionText: root.activeFeed === "calendar"', dashboard)
        self.assertIn("onActionTriggered: controller.refreshDashboard()", dashboard)
        self.assertIn("diagnosticList.count === 0", health)
        self.assertIn('state: controller.runtimeReady ? "empty" : "loading"', health)
        self.assertIn('text: controller.remoteState === "active" ? "REMOTE LINK ACTIVE"', remote)
        self.assertIn('actionText: controller.remoteState === "error" ? "RETRY STATUS"', remote)
        self.assertNotIn('controller.remoteState === "stopping" ? "loading"\n                    : "empty"', remote)

    def test_audio_and_avatar_failures_can_be_retried(self):
        audio = _read(QML / "AudioApp.qml")
        avatar = _read(QML / "AvatarApp.qml")
        controller = _read(CONTROLLER)

        self.assertIn('controller.audioStatus !== "ready"', audio)
        self.assertIn('actionText: controller.muted ? "UNMUTE"', audio)
        self.assertIn("controller.retryAudioVisualizer()", audio)
        self.assertIn('actionText: state === "error" ? "RETRY AVATAR"', avatar)
        self.assertIn("controller.reloadAvatar()", avatar)
        self.assertIn("def retryAudioVisualizer(self)", controller)
        self.assertIn("def reloadAvatar(self)", controller)


if __name__ == "__main__":
    unittest.main()
