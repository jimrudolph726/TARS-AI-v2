"""Deterministic tests for bounded QML runtime performance measurements."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modules.module_ui_performance import (
    PERFORMANCE_BUDGETS,
    RuntimePerformanceMonitor,
    percentile,
)


ROOT = Path(__file__).resolve().parents[1]


def _resources(rss: float = 100.0, threads: int = 10, descriptors: int = 20):
    return {
        "rss_mb": rss,
        "native_threads": threads,
        "python_threads": 4,
        "file_descriptors": descriptors,
    }


class RuntimePerformanceMonitorTests(unittest.TestCase):
    def test_percentile_interpolates_and_empty_is_zero(self):
        self.assertEqual(0.0, percentile([], 0.95))
        self.assertEqual(2.5, percentile([1, 2, 3, 4], 0.5))

    def test_cpu_cold_start_frames_and_heartbeat_are_measured(self):
        monitor = RuntimePerformanceMonitor(
            started_at=0.0,
            monotonic=lambda: 0.0,
            process_time=lambda: 0.0,
            cpu_count=4,
        )
        monitor.record_qml_frame(1.0)
        monitor.record_qml_frame(1.1)
        monitor.record_qml_frame(1.2)
        monitor.record_camera_frame(1.0)
        monitor.record_camera_frame(1.1)
        monitor.record_ui_heartbeat(1.0)
        monitor.record_ui_heartbeat(1.30)
        monitor.sample(
            state="STANDBY",
            temperature_c=51,
            camera_preview=True,
            camera_session=True,
            audio_stream=True,
            conversation_rows=2,
            resources=_resources(),
            now=2.0,
            process_cpu_time=0.4,
        )
        monitor.mark_runtime_ready(12.5)
        snapshot = monitor.snapshot(2.0)

        self.assertEqual(12.5, snapshot["coldStartSeconds"])
        self.assertEqual(5.0, snapshot["processCpuPercent"])
        self.assertAlmostEqual(10.0, snapshot["qmlFps"])
        self.assertAlmostEqual(10.0, snapshot["cameraFps"])
        self.assertAlmostEqual(50.0, snapshot["uiLagP95Ms"])

    def test_feature_close_records_settled_resource_delta(self):
        monitor = RuntimePerformanceMonitor(
            started_at=0.0,
            monotonic=lambda: 0.0,
            process_time=lambda: 0.0,
            cpu_count=4,
        )
        monitor.sample(
            state="STANDBY", temperature_c=50, camera_preview=False,
            camera_session=False, audio_stream=True, conversation_rows=0,
            resources=_resources(100, 10, 20), now=1.0, process_cpu_time=0.1,
        )
        monitor.change_feature("app:dashboard", now=1.0)
        monitor.change_feature("main", now=2.0)
        monitor.sample(
            state="STANDBY", temperature_c=50, camera_preview=False,
            camera_session=False, audio_stream=True, conversation_rows=0,
            resources=_resources(106, 11, 20), now=4.0, process_cpu_time=0.2,
        )
        snapshot = monitor.snapshot(4.0)

        self.assertEqual(1, snapshot["featureCycles"])
        self.assertEqual(6.0, snapshot["maxFeatureCycleGrowthMb"])
        self.assertEqual(1, monitor.report()["feature_cycles"][0]["thread_delta"])

    def test_budget_violations_are_explicit_diagnostics(self):
        monitor = RuntimePerformanceMonitor(
            started_at=0.0,
            monotonic=lambda: 0.0,
            process_time=lambda: 0.0,
            cpu_count=1,
        )
        monitor.sample(
            state="STANDBY", temperature_c=83, camera_preview=False,
            camera_session=True, audio_stream=False, conversation_rows=40,
            resources=_resources(PERFORMANCE_BUDGETS["rss_error_mb"] + 1, 30, 50),
            now=2.0, process_cpu_time=1.8,
        )
        monitor.sample(
            state="STANDBY", temperature_c=83, camera_preview=False,
            camera_session=True, audio_stream=False, conversation_rows=40,
            resources=_resources(PERFORMANCE_BUDGETS["rss_error_mb"] + 1, 30, 50),
            now=4.0, process_cpu_time=3.6,
        )
        states = {item["label"]: item["state"] for item in monitor.diagnostics(4.0)}

        self.assertEqual("error", states["IDLE CPU"])
        self.assertEqual("error", states["PROCESS MEMORY"])
        self.assertEqual("error", states["THERMAL"])
        self.assertEqual("warning", states["SHARED AUDIO STREAM"])

    def test_report_write_is_atomic_and_samples_are_bounded(self):
        monitor = RuntimePerformanceMonitor(
            started_at=0.0,
            monotonic=lambda: 0.0,
            process_time=lambda: 0.0,
            sample_limit=60,
        )
        for index in range(80):
            monitor.sample(
                state="STANDBY", temperature_c=50, camera_preview=False,
                camera_session=False, audio_stream=True, conversation_rows=0,
                resources=_resources(), now=float(index + 1),
                process_cpu_time=float(index) * 0.01,
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "performance.json"
            monitor.write_report(path)
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(60, len(report["samples"]))
            self.assertFalse(path.with_suffix(".json.tmp").exists())


class PerformanceWiringTests(unittest.TestCase):
    def test_qml_and_controller_measure_completed_work(self):
        app = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
        controller = (ROOT / "src" / "modules" / "module_ui_qml.py").read_text(
            encoding="utf-8"
        )
        main = (ROOT / "src" / "qml" / "main" / "TarsMain.qml").read_text(
            encoding="utf-8"
        )
        health = (ROOT / "src" / "qml" / "main" / "SystemHealthApp.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("window.frameSwapped.connect(controller.recordQmlFrame)", app)
        self.assertIn("self._performance.record_camera_frame()", controller)
        self.assertIn("def exportPerformanceReport(self)", controller)
        self.assertIn("controller.setActiveUiFeature(performanceFeatureName())", main)
        self.assertIn('text: "PERFORMANCE"', health)
        self.assertIn("controller.performanceDiagnostics", health)
        self.assertIn("controller.exportPerformanceReport()", health)


if __name__ == "__main__":
    unittest.main()
