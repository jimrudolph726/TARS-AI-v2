#!/usr/bin/env python3
"""Sample a running TARS process during a repeatable performance scenario.

Run this from a second Raspberry Pi terminal while the main interface is
active.  The built-in System Health monitor captures QML/camera FPS and
feature lifecycle events; this probe independently records OS-level CPU,
memory, thread, descriptor, and temperature data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from modules.module_ui_performance import (  # noqa: E402
    PERFORMANCE_BUDGETS,
    percentile,
    read_process_resources,
)


def _find_tars_pid() -> int:
    if os.name != "posix":
        raise RuntimeError("automatic process discovery requires Linux; pass --pid")
    candidates = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="ignore"
            )
            working_directory = os.readlink(entry / "cwd")
        except OSError:
            continue
        if "app.py" in command and (
            "TARS-AI-v2" in command or "TARS-AI-v2" in working_directory
        ):
            candidates.append(int(entry.name))
    if not candidates:
        raise RuntimeError("no running TARS-AI-v2 app.py process was found")
    return max(candidates)


def _process_cpu_seconds(pid: int) -> float:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    fields = stat[stat.rfind(")") + 2:].split()
    ticks = int(fields[11]) + int(fields[12])
    return ticks / float(os.sysconf("SC_CLK_TCK"))


def _temperature_c() -> float | None:
    try:
        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text(encoding="utf-8")
        return float(raw.strip()) / 1000.0
    except (OSError, ValueError):
        return None


def summarize_samples(samples: list[dict[str, float | int | None]]) -> dict[str, object]:
    if not samples:
        return {}
    cpu = [float(sample["cpu_percent"]) for sample in samples]
    rss = [float(sample["rss_mb"]) for sample in samples]
    threads = [int(sample["native_threads"]) for sample in samples]
    descriptors = [int(sample["file_descriptors"]) for sample in samples]
    temperatures = [
        float(sample["temperature_c"])
        for sample in samples
        if sample["temperature_c"] is not None
    ]
    return {
        "sample_count": len(samples),
        "cpu_average_percent": round(sum(cpu) / len(cpu), 2),
        "cpu_p95_percent": round(percentile(cpu, 0.95), 2),
        "cpu_max_percent": round(max(cpu), 2),
        "rss_start_mb": round(rss[0], 2),
        "rss_end_mb": round(rss[-1], 2),
        "rss_peak_mb": round(max(rss), 2),
        "rss_growth_mb": round(rss[-1] - rss[0], 2),
        "thread_start": threads[0],
        "thread_end": threads[-1],
        "thread_peak": max(threads),
        "descriptor_start": descriptors[0],
        "descriptor_end": descriptors[-1],
        "descriptor_peak": max(descriptors),
        "temperature_average_c": round(sum(temperatures) / len(temperatures), 1)
            if temperatures else None,
        "temperature_peak_c": round(max(temperatures), 1) if temperatures else None,
    }


def _budget_verdict(summary: dict[str, object], scenario: str) -> dict[str, str]:
    budgets = PERFORMANCE_BUDGETS
    cpu_warning = budgets[
        "listening_cpu_warning_percent" if scenario == "listening"
        else "idle_cpu_warning_percent"
    ]
    cpu_error = budgets[
        "listening_cpu_error_percent" if scenario == "listening"
        else "idle_cpu_error_percent"
    ]
    if scenario in ("camera", "applications", "conversations"):
        cpu_warning, cpu_error = 55.0, 80.0

    def verdict(value: float, warning: float, error: float) -> str:
        return "error" if value >= error else "warning" if value >= warning else "ok"

    temperature = summary.get("temperature_peak_c")
    return {
        "cpu": verdict(float(summary["cpu_p95_percent"]), cpu_warning, cpu_error),
        "memory": verdict(
            float(summary["rss_peak_mb"]),
            budgets["rss_warning_mb"],
            budgets["rss_error_mb"],
        ),
        "memory_growth": verdict(
            max(0.0, float(summary["rss_growth_mb"])),
            budgets["long_run_growth_warning_mb"],
            budgets["long_run_growth_error_mb"],
        ),
        "temperature": "unavailable" if temperature is None else verdict(
            float(temperature),
            budgets["temperature_warning_c"],
            budgets["temperature_error_c"],
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, help="running TARS app.py process ID")
    parser.add_argument(
        "--scenario",
        choices=("idle", "listening", "camera", "applications", "conversations"),
        default="idle",
    )
    parser.add_argument("--duration", type=float, default=300.0, help="seconds to sample")
    parser.add_argument("--interval", type=float, default=1.0, help="sample interval in seconds")
    parser.add_argument("--output", type=Path, help="JSON report path")
    args = parser.parse_args()

    pid = args.pid or _find_tars_pid()
    if not Path(f"/proc/{pid}").exists():
        raise SystemExit(f"PID {pid} is not running")

    duration = max(1.0, args.duration)
    interval = max(0.25, args.interval)
    cpu_count = max(1, os.cpu_count() or 1)
    started = time.monotonic()
    previous_wall = started
    previous_cpu = _process_cpu_seconds(pid)
    samples: list[dict[str, float | int | None]] = []

    print(
        f"Profiling PID {pid} · scenario={args.scenario} · "
        f"duration={duration:.0f}s · Ctrl+C stops early"
    )
    try:
        while time.monotonic() - started < duration:
            time.sleep(interval)
            now = time.monotonic()
            if not Path(f"/proc/{pid}").exists():
                print("TARS process exited during the probe")
                break
            cpu_time = _process_cpu_seconds(pid)
            wall_delta = max(0.000001, now - previous_wall)
            cpu_percent = min(
                100.0,
                ((cpu_time - previous_cpu) / wall_delta) * 100.0 / cpu_count,
            )
            previous_wall, previous_cpu = now, cpu_time
            resources = read_process_resources(pid)
            samples.append({
                "elapsed_seconds": round(now - started, 2),
                "cpu_percent": round(cpu_percent, 2),
                "rss_mb": float(resources["rss_mb"]),
                "native_threads": int(resources["native_threads"]),
                "file_descriptors": int(resources["file_descriptors"]),
                "temperature_c": _temperature_c(),
            })
            if len(samples) % max(1, round(10.0 / interval)) == 0:
                latest = samples[-1]
                print(
                    f"{latest['elapsed_seconds']:>6.0f}s  "
                    f"CPU {latest['cpu_percent']:>5.1f}%  "
                    f"RSS {latest['rss_mb']:>7.1f} MB  "
                    f"TEMP {latest['temperature_c'] if latest['temperature_c'] is not None else '--'}"
                )
    except KeyboardInterrupt:
        print("Probe stopped by user")

    summary = summarize_samples(samples)
    if not summary:
        raise SystemExit("No samples were collected")
    report = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "pid": pid,
        "scenario": args.scenario,
        "budgets": PERFORMANCE_BUDGETS,
        "verdict": _budget_verdict(summary, args.scenario),
        "summary": summary,
        "samples": samples,
    }
    output = args.output or (
        SRC / "logs" /
        f"performance-probe-{args.scenario}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    os.replace(temporary, output)

    print(json.dumps({"verdict": report["verdict"], "summary": summary}, indent=2))
    print(f"Report saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
