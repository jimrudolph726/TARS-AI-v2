"""Low-overhead performance measurements for the native QML runtime.

The monitor is deliberately presentation- and hardware-neutral.  Qt supplies
render and feature lifecycle events, while the controller supplies camera,
audio, temperature, and conversation state.  Samples are bounded so leaving
TARS running for days cannot make the profiler itself a memory leak.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


PERFORMANCE_BUDGETS: dict[str, float] = {
    "cold_start_warning_seconds": 45.0,
    "cold_start_error_seconds": 90.0,
    "idle_cpu_warning_percent": 25.0,
    "idle_cpu_error_percent": 45.0,
    "listening_cpu_warning_percent": 45.0,
    "listening_cpu_error_percent": 70.0,
    "rss_warning_mb": 1536.0,
    "rss_error_mb": 2304.0,
    "long_run_growth_warning_mb": 100.0,
    "long_run_growth_error_mb": 256.0,
    "qml_fps_warning": 45.0,
    "qml_fps_error": 30.0,
    "camera_fps_warning": 8.0,
    "camera_fps_error": 5.0,
    "ui_lag_warning_ms": 40.0,
    "ui_lag_error_ms": 120.0,
    "temperature_warning_c": 75.0,
    "temperature_error_c": 82.0,
    "feature_cycle_growth_warning_mb": 8.0,
    "feature_cycle_growth_error_mb": 25.0,
    "thread_growth_warning": 4.0,
    "thread_growth_error": 10.0,
}


def percentile(values: list[float], fraction: float) -> float:
    """Return a linearly interpolated percentile for a short sample list."""
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def read_process_resources(pid: Optional[int] = None) -> dict[str, float | int]:
    """Read current process RSS, native threads, and file descriptors.

    Linux uses ``/proc`` without adding a dependency.  Development platforms
    fall back to psutil when available and otherwise report zero for metrics
    the standard library cannot provide accurately.
    """
    process_id = int(pid or os.getpid())
    rss_mb = 0.0
    native_threads = 0
    file_descriptors = 0

    status_path = Path(f"/proc/{process_id}/status")
    if status_path.is_file():
        try:
            for line in status_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    rss_mb = float(line.split()[1]) / 1024.0
                elif line.startswith("Threads:"):
                    native_threads = int(line.split()[1])
            fd_path = Path(f"/proc/{process_id}/fd")
            if fd_path.is_dir():
                file_descriptors = sum(1 for _ in fd_path.iterdir())
        except (OSError, ValueError, IndexError):
            pass
    else:
        try:
            import psutil

            process = psutil.Process(process_id)
            rss_mb = float(process.memory_info().rss) / (1024.0 * 1024.0)
            native_threads = int(process.num_threads())
            try:
                file_descriptors = int(process.num_fds())
            except (AttributeError, OSError):
                file_descriptors = 0
        except Exception:
            pass

    return {
        "rss_mb": round(rss_mb, 2),
        "native_threads": native_threads,
        "python_threads": threading.active_count(),
        "file_descriptors": file_descriptors,
    }


def _high_state(value: float, warning: float, error: float) -> str:
    if value >= error:
        return "error"
    if value >= warning:
        return "warning"
    return "ok"


def _low_state(value: float, warning: float, error: float) -> str:
    if value < error:
        return "error"
    if value < warning:
        return "warning"
    return "ok"


class RuntimePerformanceMonitor:
    """Bounded runtime recorder with explicit Raspberry Pi 5 budgets."""

    def __init__(
        self,
        *,
        started_at: Optional[float] = None,
        monotonic: Callable[[], float] = time.monotonic,
        process_time: Callable[[], float] = time.process_time,
        cpu_count: Optional[int] = None,
        sample_limit: int = 900,
    ) -> None:
        self._monotonic = monotonic
        self._process_time = process_time
        self._cpu_count = max(1, int(cpu_count or os.cpu_count() or 1))
        self._started_at = float(started_at if started_at is not None else monotonic())
        self._last_wall = self._started_at
        self._last_cpu_time = float(process_time())
        self._runtime_ready_at: Optional[float] = None
        self._cold_start_seconds = 0.0
        self._ready_rss_mb: Optional[float] = None
        self._ready_native_threads: Optional[int] = None
        self._samples: deque[dict[str, object]] = deque(maxlen=max(60, sample_limit))
        self._state_cpu: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=120))
        self._camera_frames: deque[float] = deque(maxlen=180)
        self._qml_frames: deque[float] = deque(maxlen=360)
        self._heartbeat_lag_ms: deque[float] = deque(maxlen=240)
        self._last_heartbeat: Optional[float] = None
        self._latest: dict[str, object] = {}
        self._active_feature = "main"
        self._active_feature_baseline: Optional[dict[str, object]] = None
        self._pending_feature_closes: list[dict[str, object]] = []
        self._feature_cycles: deque[dict[str, object]] = deque(maxlen=120)

    def mark_runtime_ready(self, now: Optional[float] = None) -> None:
        if self._runtime_ready_at is not None:
            return
        self._runtime_ready_at = float(now if now is not None else self._monotonic())
        self._cold_start_seconds = max(0.0, self._runtime_ready_at - self._started_at)
        if self._latest:
            self._ready_rss_mb = float(self._latest.get("rss_mb", 0.0))
            self._ready_native_threads = int(self._latest.get("native_threads", 0))

    @staticmethod
    def _rate(events: deque[float], now: float, window_seconds: float = 3.0) -> float:
        recent = [stamp for stamp in events if now - stamp <= window_seconds]
        if len(recent) < 2:
            return 0.0
        elapsed = recent[-1] - recent[0]
        return (len(recent) - 1) / elapsed if elapsed > 0 else 0.0

    def record_camera_frame(self, now: Optional[float] = None) -> None:
        self._camera_frames.append(float(now if now is not None else self._monotonic()))

    def record_qml_frame(self, now: Optional[float] = None) -> None:
        self._qml_frames.append(float(now if now is not None else self._monotonic()))

    def record_ui_heartbeat(
        self,
        now: Optional[float] = None,
        expected_interval: float = 0.25,
    ) -> None:
        stamp = float(now if now is not None else self._monotonic())
        if self._last_heartbeat is not None:
            lag_ms = max(0.0, stamp - self._last_heartbeat - expected_interval) * 1000.0
            self._heartbeat_lag_ms.append(lag_ms)
        self._last_heartbeat = stamp

    def change_feature(self, name: str, now: Optional[float] = None) -> None:
        normalized = str(name or "main")
        if normalized == self._active_feature:
            return
        stamp = float(now if now is not None else self._monotonic())
        if self._active_feature != "main" and self._active_feature_baseline:
            pending = dict(self._active_feature_baseline)
            pending["feature"] = self._active_feature
            pending["due_at"] = stamp + 1.5
            self._pending_feature_closes.append(pending)
        self._active_feature = normalized
        if normalized == "main" or not self._latest:
            self._active_feature_baseline = None
        else:
            self._active_feature_baseline = {
                "opened_at": stamp,
                "rss_mb": float(self._latest.get("rss_mb", 0.0)),
                "native_threads": int(self._latest.get("native_threads", 0)),
                "file_descriptors": int(self._latest.get("file_descriptors", 0)),
            }

    def sample(
        self,
        *,
        state: str,
        temperature_c: Optional[float],
        camera_preview: bool,
        camera_session: bool,
        audio_stream: bool,
        conversation_rows: int,
        resources: Optional[dict[str, float | int]] = None,
        now: Optional[float] = None,
        process_cpu_time: Optional[float] = None,
    ) -> dict[str, object]:
        stamp = float(now if now is not None else self._monotonic())
        cpu_time = float(
            process_cpu_time if process_cpu_time is not None else self._process_time()
        )
        wall_delta = max(0.000001, stamp - self._last_wall)
        cpu_delta = max(0.0, cpu_time - self._last_cpu_time)
        normalized_cpu = min(100.0, (cpu_delta / wall_delta) * 100.0 / self._cpu_count)
        self._last_wall = stamp
        self._last_cpu_time = cpu_time

        process = dict(resources or read_process_resources())
        sample = {
            "timestamp": round(stamp, 3),
            "state": str(state).upper(),
            "process_cpu_percent": round(normalized_cpu, 2),
            "rss_mb": round(float(process.get("rss_mb", 0.0)), 2),
            "native_threads": int(process.get("native_threads", 0)),
            "python_threads": int(process.get("python_threads", 0)),
            "file_descriptors": int(process.get("file_descriptors", 0)),
            "temperature_c": None if temperature_c is None else round(float(temperature_c), 1),
            "camera_preview": bool(camera_preview),
            "camera_session": bool(camera_session),
            "audio_stream": bool(audio_stream),
            "conversation_rows": max(0, int(conversation_rows)),
            "active_feature": self._active_feature,
        }
        self._latest = sample
        self._samples.append(sample)
        if len(self._samples) > 1:
            self._state_cpu[sample["state"]].append(normalized_cpu)

        if self._runtime_ready_at is not None and self._ready_rss_mb is None:
            self._ready_rss_mb = float(sample["rss_mb"])
            self._ready_native_threads = int(sample["native_threads"])

        remaining = []
        for pending in self._pending_feature_closes:
            if stamp < float(pending["due_at"]):
                remaining.append(pending)
                continue
            self._feature_cycles.append({
                "feature": str(pending["feature"]),
                "duration_seconds": round(stamp - float(pending["opened_at"]), 2),
                "rss_delta_mb": round(float(sample["rss_mb"]) - float(pending["rss_mb"]), 2),
                "thread_delta": int(sample["native_threads"]) - int(pending["native_threads"]),
                "fd_delta": int(sample["file_descriptors"]) - int(pending["file_descriptors"]),
            })
        self._pending_feature_closes = remaining
        return self.snapshot(stamp)

    def _cpu_average(self, states: tuple[str, ...]) -> float:
        values = [value for state in states for value in self._state_cpu.get(state, ())]
        return sum(values) / len(values) if values else 0.0

    def snapshot(self, now: Optional[float] = None) -> dict[str, object]:
        stamp = float(now if now is not None else self._monotonic())
        latest = self._latest
        rss_mb = float(latest.get("rss_mb", 0.0))
        native_threads = int(latest.get("native_threads", 0))
        feature_deltas = [max(0.0, float(item["rss_delta_mb"])) for item in self._feature_cycles]
        return {
            "coldStartSeconds": round(self._cold_start_seconds, 2),
            "runtimeReadyMeasured": self._runtime_ready_at is not None,
            "processCpuPercent": float(latest.get("process_cpu_percent", 0.0)),
            "idleCpuPercent": round(self._cpu_average(("STANDBY", "IDLE")), 2),
            "listeningCpuPercent": round(self._cpu_average(("LISTENING",)), 2),
            "rssMb": round(rss_mb, 2),
            "memoryGrowthMb": round(
                rss_mb - self._ready_rss_mb if self._ready_rss_mb is not None else 0.0,
                2,
            ),
            "nativeThreads": native_threads,
            "threadGrowth": native_threads - self._ready_native_threads
                if self._ready_native_threads is not None else 0,
            "fileDescriptors": int(latest.get("file_descriptors", 0)),
            "temperatureC": latest.get("temperature_c"),
            "qmlFps": round(self._rate(self._qml_frames, stamp), 1),
            "cameraFps": round(self._rate(self._camera_frames, stamp), 1),
            "uiLagP95Ms": round(percentile(list(self._heartbeat_lag_ms), 0.95), 1),
            "cameraPreviewActive": bool(latest.get("camera_preview", False)),
            "cameraSessionActive": bool(latest.get("camera_session", False)),
            "audioStreamActive": bool(latest.get("audio_stream", False)),
            "conversationRows": int(latest.get("conversation_rows", 0)),
            "activeFeature": self._active_feature,
            "featureCycles": len(self._feature_cycles),
            "maxFeatureCycleGrowthMb": round(max(feature_deltas, default=0.0), 2),
        }

    def diagnostics(self, now: Optional[float] = None) -> list[dict[str, str]]:
        metrics = self.snapshot(now)
        budgets = PERFORMANCE_BUDGETS
        diagnostics: list[dict[str, str]] = []

        if metrics["runtimeReadyMeasured"]:
            cold = float(metrics["coldStartSeconds"])
            diagnostics.append({
                "label": "COLD START",
                "value": f"{cold:.1f} S",
                "state": _high_state(cold, budgets["cold_start_warning_seconds"], budgets["cold_start_error_seconds"]),
                "detail": "Target ≤45 s; investigate model or hardware initialization above 90 s",
            })
        else:
            diagnostics.append({
                "label": "COLD START", "value": "MEASURING", "state": "warning",
                "detail": "Timer stops when the runtime reports ready",
            })

        for label, key, warning_key, error_key, detail in (
            ("IDLE CPU", "idleCpuPercent", "idle_cpu_warning_percent", "idle_cpu_error_percent", "Normalized across all CPU cores while STANDBY"),
            ("LISTENING CPU", "listeningCpuPercent", "listening_cpu_warning_percent", "listening_cpu_error_percent", "Normalized across all CPU cores while LISTENING"),
        ):
            value = float(metrics[key])
            measured = bool(self._state_cpu.get("STANDBY") or self._state_cpu.get("IDLE")) if key == "idleCpuPercent" else bool(self._state_cpu.get("LISTENING"))
            diagnostics.append({
                "label": label,
                "value": f"{value:.1f}%" if measured else "MEASURING",
                "state": _high_state(value, budgets[warning_key], budgets[error_key]) if measured else "info",
                "detail": detail,
            })

        rss = float(metrics["rssMb"])
        growth = float(metrics["memoryGrowthMb"])
        memory_state = max(
            (_high_state(rss, budgets["rss_warning_mb"], budgets["rss_error_mb"]),
             _high_state(max(0.0, growth), budgets["long_run_growth_warning_mb"], budgets["long_run_growth_error_mb"])),
            key=("ok", "info", "warning", "error").index,
        )
        diagnostics.append({
            "label": "PROCESS MEMORY",
            "value": f"{rss:.0f} MB",
            "state": memory_state,
            "detail": f"{growth:+.0f} MB since runtime ready; target long-run growth <100 MB",
        })

        qml_fps = float(metrics["qmlFps"])
        diagnostics.append({
            "label": "QML RENDER",
            "value": f"{qml_fps:.1f} FPS" if qml_fps else "MEASURING",
            "state": _low_state(qml_fps, budgets["qml_fps_warning"], budgets["qml_fps_error"]) if qml_fps else "info",
            "detail": "Frame-swapped rate; target ≥45 FPS while animations are active",
        })

        lag = float(metrics["uiLagP95Ms"])
        diagnostics.append({
            "label": "UI EVENT LOOP",
            "value": f"{lag:.0f} MS P95",
            "state": _high_state(lag, budgets["ui_lag_warning_ms"], budgets["ui_lag_error_ms"]),
            "detail": "Delay beyond the 250 ms UI heartbeat; target <40 ms",
        })

        if metrics["cameraPreviewActive"]:
            camera_fps = float(metrics["cameraFps"])
            diagnostics.append({
                "label": "CAMERA PREVIEW",
                "value": f"{camera_fps:.1f} FPS" if camera_fps else "STARTING",
                "state": _low_state(camera_fps, budgets["camera_fps_warning"], budgets["camera_fps_error"]) if camera_fps else "warning",
                "detail": "QML preview target ≥8 FPS",
            })
        else:
            diagnostics.append({
                "label": "CAMERA PREVIEW",
                "value": "CLOSED",
                "state": "info",
                "detail": "Shared capture session is " + ("available" if metrics["cameraSessionActive"] else "stopped"),
            })

        temperature = metrics["temperatureC"]
        diagnostics.append({
            "label": "THERMAL",
            "value": f"{float(temperature):.0f}°C" if temperature is not None else "UNAVAILABLE",
            "state": _high_state(float(temperature), budgets["temperature_warning_c"], budgets["temperature_error_c"]) if temperature is not None else "disabled",
            "detail": "Target <75°C; critical investigation threshold 82°C",
        })

        cycle_growth = float(metrics["maxFeatureCycleGrowthMb"])
        diagnostics.append({
            "label": "APP LIFECYCLE",
            "value": f"{metrics['featureCycles']} CYCLES",
            "state": _high_state(cycle_growth, budgets["feature_cycle_growth_warning_mb"], budgets["feature_cycle_growth_error_mb"]) if metrics["featureCycles"] else "info",
            "detail": f"Largest settled close delta {cycle_growth:.1f} MB; lazy caches are retained in the report",
        })

        thread_growth = int(metrics["threadGrowth"])
        diagnostics.append({
            "label": "THREAD STABILITY",
            "value": f"{metrics['nativeThreads']} THREADS",
            "state": _high_state(max(0, thread_growth), budgets["thread_growth_warning"], budgets["thread_growth_error"]),
            "detail": f"{thread_growth:+d} native threads since runtime ready",
        })
        diagnostics.append({
            "label": "SHARED AUDIO STREAM",
            "value": "ACTIVE" if metrics["audioStreamActive"] else "STOPPED",
            "state": "ok" if metrics["audioStreamActive"] else "warning",
            "detail": "Controller-owned for the main waveform and Audio Timeline; closing the app does not duplicate it",
        })
        return diagnostics

    def report(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "pid": os.getpid(),
            "budgets": PERFORMANCE_BUDGETS,
            "summary": self.snapshot(),
            "diagnostics": self.diagnostics(),
            "feature_cycles": list(self._feature_cycles),
            "samples": list(self._samples),
        }

    def write_report(self, path: Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(self.report(), indent=2), encoding="utf-8")
        os.replace(temporary, destination)
        return destination
