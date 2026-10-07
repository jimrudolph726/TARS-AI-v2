"""Background lifecycle for the TARS robot services.

The PySide6 event loop must remain on the process main thread.  This worker
performs the existing speech, model, memory, servo, camera, and controller
initialization without blocking QML rendering or touch input.
"""

from __future__ import annotations

import subprocess
import threading
import traceback


class TarsRuntime(threading.Thread):
    """Own all non-Qt TARS services and shut them down as one unit."""

    def __init__(self, config: dict, ui_controller, debug_mode: bool = False):
        super().__init__(name="TarsRuntime", daemon=True)
        self.config = config
        self.ui = ui_controller
        self.debug_mode = debug_mode
        self.shutdown_event = threading.Event()
        self._shutdown_device = False
        self._startup_failed = False

        self.battery = None
        self.cpu_temp = None
        self.stt_manager = None
        self.memory_manager = None
        self.bt_controller_thread = None
        self._state_callback = None

    def request_stop(self) -> None:
        self.shutdown_event.set()
        if not self.is_alive():
            self.ui.notify_runtime_stopped()

    def request_shutdown(self) -> None:
        self._shutdown_device = True
        self.shutdown_event.set()
        if not self.is_alive():
            self._power_off()

    def _status(self, text: str, ready: bool = False) -> None:
        self.ui.set_runtime_status(text, ready)
        try:
            from modules.module_messageQue import queue_message

            queue_message(f"LOAD: {text}")
        except Exception:
            pass

    def run(self) -> None:
        try:
            self._initialize_and_run()
        except Exception as exc:
            self._startup_failed = True
            message = f"STARTUP FAILED: {type(exc).__name__}: {exc}"
            self.ui.set_runtime_status(message, False)
            self.ui.update_data("SYSTEM", message, "ERROR")
            try:
                from modules.module_messageQue import queue_message

                queue_message(f"ERROR: {message}")
            except Exception:
                pass
            traceback.print_exc()
        finally:
            self._cleanup()
            if self._shutdown_device:
                self._power_off()
            elif self.shutdown_event.is_set():
                self.ui.notify_runtime_stopped()

    def _initialize_and_run(self) -> None:
        from modules.module_messageQue import queue_message
        from modules.module_config import should_use_lite_memory

        device_info = self.config.get("_device", {})
        raspberry_version = device_info.get("raspberry_version", "pi5")

        self._status(f"LOADING TARS-AI ON {raspberry_version.upper()}")

        from modules.module_tts import update_tts_settings

        if self.config["TTS"]["ttsoption"] == "xttsv2":
            update_tts_settings(self.config["TTS"]["ttsurl"])

        try:
            import modules.module_heartbeat  # noqa: F401

            queue_message("LOAD: Heartbeat module ready")
        except Exception as exc:
            queue_message(f"WARNING: Heartbeat module not available: {exc}")

        self._status("DISCOVERING SKILLS")
        from modules.module_skills import initialize_skills

        initialize_skills()
        if self.shutdown_event.is_set():
            return

        self._status("STARTING HARDWARE TELEMETRY")
        if self.config["BATTERY"].get("battery_enabled", False):
            try:
                from modules.module_battery import BatteryModule

                self.battery = BatteryModule()
                self.battery.start()
            except Exception as exc:
                queue_message(f"WARNING: Battery module not available: {exc}")

        from modules.module_cputemp import CPUTempModule

        self.cpu_temp = CPUTempModule()
        self.ui.attach_sources(battery=self.battery, cpu=self.cpu_temp)

        self._start_web_ui()
        if self.shutdown_event.is_set():
            return

        self._status("LOADING CHARACTER AND MEMORY")
        from modules.module_character import CharacterManager

        if should_use_lite_memory(self.config):
            from modules.module_memory_lite import MemoryManagerLite as MemoryManager
        else:
            from modules.module_memory import MemoryManager

        character_manager = CharacterManager(config=self.config)
        self.memory_manager = MemoryManager(
            config=self.config,
            char_name=character_manager.char_name,
            char_greeting=character_manager.char_greeting,
            ui_manager=self.ui,
        )
        if self.shutdown_event.is_set():
            return

        self._status("INITIALIZING SPEECH SYSTEM")
        from modules.module_llm import initialize_manager_llm, process_completion
        from modules.module_main import (
            initialize_managers,
            post_utterance_callback,
            start_bt_controller_thread,
            startup_initialization,
            utterance_callback,
            wake_word_callback,
        )
        from modules.module_state import (
            TarsState,
            on_state_change,
            register_stt_manager,
            remove_state_change,
            set_tars_state,
        )
        from modules.module_stt import STTManager
        from modules import module_servoctl

        self.stt_manager = STTManager(
            config=self.config,
            shutdown_event=self.shutdown_event,
            ui_manager=self.ui,
        )
        if self.debug_mode:
            self.stt_manager.DEBUG = True
        self.stt_manager.set_wake_word_callback(wake_word_callback)
        self.stt_manager.set_utterance_callback(utterance_callback)
        self.stt_manager.set_post_utterance_callback(post_utterance_callback)
        self.stt_manager.set_preemptive_llm_callback(process_completion)
        self.ui.attach_sources(stt=self.stt_manager)

        def pause_for_movement():
            self.ui.pause()
            if self.stt_manager:
                self.stt_manager.pause()

        def resume_after_movement():
            self.ui.resume()
            if self.stt_manager:
                self.stt_manager.resume()

        module_servoctl.set_movement_callbacks(
            on_start=pause_for_movement,
            on_end=resume_after_movement,
        )

        self._state_callback = lambda old, new: self.ui.set_tars_status(new.value)
        on_state_change(self._state_callback)
        set_tars_state(TarsState.BOOTING)

        self._start_speaker_identity()
        initialize_managers(
            self.memory_manager,
            character_manager,
            self.stt_manager,
            self.ui,
            self.shutdown_event,
            self.battery,
        )
        initialize_manager_llm(self.memory_manager, character_manager)
        if self.shutdown_event.is_set():
            remove_state_change(self._state_callback)
            self._state_callback = None
            return

        self._start_bluetooth(start_bt_controller_thread)
        self._start_vision(device_info)

        self._status("INITIALIZING SERVOS")
        startup_initialization()
        if self.shutdown_event.is_set():
            return

        register_stt_manager(self.stt_manager)
        self.stt_manager.start()
        set_tars_state(TarsState.STANDBY)

        version = "Amelia"
        queue_message(
            f"LOAD: TARS-AI OS: {version} running on {raspberry_version.upper()}"
        )
        self.ui.update_data("SYSTEM", f"TARS-AI OS: {version} running", "SYSTEM")
        self._status("ALL SYSTEMS OPERATIONAL", True)

        while not self.shutdown_event.wait(0.1):
            pass

    def _start_web_ui(self) -> None:
        if not self.config["ACCESS"].get("webui_enabled", False):
            return
        try:
            import modules.module_chatui

            port = self.config["ACCESS"].get("webui_port", 80)
            threading.Thread(
                target=modules.module_chatui.start_flask_app,
                kwargs={"port": port},
                name="ChatUI",
                daemon=True,
            ).start()
        except Exception as exc:
            from modules.module_messageQue import queue_message

            queue_message(f"WARNING: ChatUI module not available: {exc}")

    def _start_speaker_identity(self) -> None:
        from modules.module_messageQue import queue_message

        if self.config["STT"].get("speaker_id_enabled", "False").lower() == "true":
            try:
                from modules.module_speaker_id import SpeakerIDManager

                SpeakerIDManager(config=self.config).start()
                queue_message("LOAD: Speaker ID module enabled")
            except Exception as exc:
                queue_message(f"WARNING: Speaker ID module not available: {exc}")

        try:
            from modules.module_identity import IdentityManager

            sid = None
            try:
                from modules.module_speaker_id import get_speaker_id_manager

                sid = get_speaker_id_manager()
            except Exception:
                pass
            IdentityManager(speaker_id_manager=sid, ui_manager=self.ui)
            queue_message("LOAD: Identity coordinator enabled")
        except Exception as exc:
            queue_message(f"WARNING: Identity coordinator not available: {exc}")

    def _start_bluetooth(self, start_bt_controller_thread) -> None:
        if not self.config["CONTROLS"].get("enabled", False):
            return
        self.bt_controller_thread = threading.Thread(
            target=start_bt_controller_thread,
            name="BTControllerThread",
            daemon=True,
        )
        self.bt_controller_thread.start()

    def _start_vision(self, device_info: dict) -> None:
        if not self.config["VISION"].get("enabled", False):
            return
        caps = device_info.get("capabilities")
        processor = self.config["VISION"].get("vision_processor", "blip")
        if caps is not None and not caps.can_use_vision and processor not in (
            "server_hosted",
            "openai",
            "llm",
        ):
            return
        if processor != "blip":
            return
        try:
            from modules.module_vision import initialize_blip

            threading.Thread(
                target=initialize_blip,
                name="BlipInitThread",
                daemon=True,
            ).start()
        except Exception as exc:
            from modules.module_messageQue import queue_message

            queue_message(f"WARNING: Vision module not available: {exc}")

    def _cleanup(self) -> None:
        try:
            from modules.module_state import remove_state_change

            if self._state_callback is not None:
                remove_state_change(self._state_callback)
                self._state_callback = None
        except Exception:
            pass
        try:
            from modules.module_dashboard_data import flush_log

            flush_log()
        except Exception:
            pass
        if self.memory_manager is not None:
            try:
                self.memory_manager.flush()
            except Exception:
                pass
        if self.stt_manager is not None:
            try:
                self.stt_manager.stop()
            except Exception:
                pass
        try:
            from modules.module_speaker_id import get_speaker_id_manager

            sid = get_speaker_id_manager()
            if sid is not None:
                sid.stop()
        except Exception:
            pass
        if self.battery is not None:
            try:
                self.battery.stop()
            except Exception:
                pass
        if self.bt_controller_thread is not None:
            self.bt_controller_thread.join(timeout=2)
        try:
            from modules.module_cputemp import stop_thermal_monitoring

            stop_thermal_monitoring()
        except Exception:
            pass
        try:
            from modules.module_messageQue import queue_message

            queue_message("INFO: Shutdown complete.")
        except Exception:
            pass

    def _power_off(self) -> None:
        try:
            subprocess.Popen(["sudo", "shutdown", "now"])
        except Exception as exc:
            self.ui.update_data("SYSTEM", f"Shutdown command failed: {exc}", "ERROR")
            self.ui.notify_runtime_stopped()

