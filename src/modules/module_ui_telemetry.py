"""Resource collection and diagnostics assembly for the QML UI."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path


def format_uptime(seconds: float) -> str:
    total_minutes = max(0, int(seconds // 60))
    days, remaining = divmod(total_minutes, 1440)
    hours, minutes = divmod(remaining, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def collect_resource_metrics(base_dir: Path, process_started_at: float) -> dict[str, object]:
    memory_percent = 0
    disk_percent = 0
    try:
        import psutil

        memory_percent = round(float(psutil.virtual_memory().percent))
        disk_percent = round(float(psutil.disk_usage(str(base_dir)).percent))
        uptime_seconds = time.time() - float(psutil.boot_time())
    except Exception:
        try:
            import shutil
            disk = shutil.disk_usage(base_dir)
            disk_percent = round((disk.used / disk.total) * 100) if disk.total else 0
        except Exception:
            disk_percent = 0
        try:
            meminfo = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    key, value = line.split(":", 1)
                    meminfo[key] = int(value.strip().split()[0])
            total = meminfo.get("MemTotal", 0)
            available = meminfo.get("MemAvailable", 0)
            memory_percent = round(((total - available) / total) * 100) if total else 0
        except Exception:
            memory_percent = 0
        try:
            uptime_seconds = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        except Exception:
            uptime_seconds = time.monotonic() - process_started_at
    return {
        "memory_percent": memory_percent,
        "disk_percent": disk_percent,
        "uptime_text": format_uptime(uptime_seconds),
        "process_threads": threading.active_count(),
    }


def build_system_diagnostics(
    config: dict,
    *,
    runtime_ready: bool,
    runtime_status: str,
    calibration_active: bool,
    camera_error: str,
    camera_initialized: bool,
    battery,
    battery_available: bool,
    stt,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    controls = config.get("CONTROLS", {})
    movement_enabled = bool(controls.get("enabled") or controls.get("voicemovement"))
    servo_module = sys.modules.get("modules.module_servoctl")
    servo_online = bool(servo_module is not None and getattr(servo_module, "pca", None) is not None)
    if calibration_active:
        servo_value, servo_state, servo_detail = (
            "RESERVED", "warning", "Exclusive control transferred to calibration",
        )
    elif not movement_enabled:
        servo_value, servo_state, servo_detail = (
            "DISABLED", "disabled", "Movement is disabled in config.ini",
        )
    elif servo_online:
        servo_value, servo_state, servo_detail = (
            "ONLINE", "ok", "PCA9685 servo controller detected",
        )
    else:
        servo_value, servo_state, servo_detail = (
            "OFFLINE", "error", "PCA9685 is not available",
        )

    battery_enabled = bool(config.get("BATTERY", {}).get("battery_enabled", False))
    battery_online = bool(
        battery is not None and getattr(battery, "sensor_initialized", battery_available)
    )
    if not battery_enabled:
        ina_value, ina_state, ina_detail = "DISABLED", "disabled", "Battery monitoring is disabled"
    elif battery_online:
        ina_value, ina_state, ina_detail = "ONLINE", "ok", "INA260 voltage and current sensor detected"
    else:
        ina_value, ina_state, ina_detail = "OFFLINE", "error", "INA260 is not responding"

    vision_enabled = bool(config.get("VISION", {}).get("enabled", False))
    if not vision_enabled:
        camera_value, camera_state, camera_detail = "DISABLED", "disabled", "Vision is disabled in config.ini"
    elif camera_error:
        camera_value, camera_state, camera_detail = "ERROR", "error", camera_error
    elif camera_initialized:
        camera_value, camera_state, camera_detail = "ONLINE", "ok", "Camera initialized and available"
    else:
        camera_value, camera_state, camera_detail = "CONFIGURED", "info", "Camera will initialize on first use"

    hardware = [
        {"label": "SERVO CONTROLLER", "value": servo_value, "state": servo_state, "detail": servo_detail},
        {"label": "BATTERY SENSOR", "value": ina_value, "state": ina_state, "detail": ina_detail},
        {"label": "CAMERA", "value": camera_value, "state": camera_state, "detail": camera_detail},
        {
            "label": "MICROPHONE",
            "value": "ONLINE" if stt is not None else "STARTING",
            "state": "ok" if stt is not None else "warning",
            "detail": "Shared audio input and wake-word stream",
        },
    ]

    stt_config = config.get("STT", {})
    llm_config = config.get("LLM", {})
    tts_config = config.get("TTS")
    software = [
        {
            "label": "RUNTIME",
            "value": "READY" if runtime_ready else "STARTING",
            "state": "ok" if runtime_ready else "warning",
            "detail": runtime_status,
        },
        {
            "label": "SPEECH INPUT",
            "value": str(stt_config.get("stt_processor", "unknown")).upper(),
            "state": "ok" if stt is not None else "warning",
            "detail": "Active transcription backend",
        },
        {
            "label": "VOICE OUTPUT",
            "value": str(getattr(tts_config, "ttsoption", "unknown")).upper(),
            "state": "ok",
            "detail": "Configured text-to-speech backend",
        },
        {
            "label": "LANGUAGE MODEL",
            "value": str(llm_config.get("llm_backend", "unknown")).upper(),
            "state": "info",
            "detail": str(llm_config.get("openai_model") or llm_config.get("other_model") or "configured model"),
        },
    ]
    return hardware, software
