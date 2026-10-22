"""
module_main.py

Core logic module for the TARS-AI application.

"""
# === Standard Libraries ===
import os
import threading
import json
import re
import sys
import time
import asyncio

# === Custom Modules ===
from modules.module_config import load_config
from modules.module_llm import process_completion, detect_emotion, detect_emotion_from_llm, llm_execute_side_effects, _sanitize_for_tts
from modules.module_tts import play_audio_chunks, SentenceTTSPipeline
from modules.module_messageQue import queue_message
from modules.module_servoctl import initialize_servos
from modules.module_state import set_tars_state, TarsState

CONFIG = load_config()


# BT Controller
try:
    from modules.module_btcontroller import start_controls
except ImportError:
    start_controls = None

# === Constants and Globals ===
ui_manager = None
character_manager = None
memory_manager = None
stt_manager = None
shutdown_event = None
battery_module = None

# Global Variables (if needed)
stop_event = threading.Event()


_DIRECT_CAMERA_PATTERNS = (
    r"\bwhat (?:do|can) you see\b",
    r"\btell me what you see\b",
    r"\bwhat(?:'s| is) (?:in front of|around) you\b",
    r"\bdescribe (?:what you see|your view|the view|your surroundings)\b",
    r"\blook (?:at this|at me|in front of you|around)\b",
    r"\bcan you see (?:me|this|that|anything)\b",
)


def _is_direct_camera_request(text):
    """Recognize explicit live-camera requests without matching figurative 'see'."""
    normalized = str(text or "").lower().replace("’", "'")
    return any(re.search(pattern, normalized) for pattern in _DIRECT_CAMERA_PATTERNS)


def _route_direct_camera_request(message_dict, user_text):
    """Force explicit vision requests through the camera skill, not LLM guessing."""
    if message_dict.get("preemptive_llm_result") is not None:
        return
    if not _is_direct_camera_request(user_text):
        return

    try:
        from modules.module_skills import get_skill_manager

        skills = get_skill_manager()
        if skills is None or not skills.is_enabled("capture_camera_view"):
            queue_message(
                "WARNING: Direct camera request detected, but capture_camera_view is disabled"
            )
            message_dict["preemptive_llm_result"] = {
                "reply": "Camera analysis is disabled in the skills configuration.",
                "function_calls": [],
                "new_memories": [],
            }
            return
    except Exception as exc:
        queue_message(f"WARNING: Unable to verify camera skill availability: {exc}")
        return

    message_dict["preemptive_llm_result"] = {
        # Leave the initial reply empty. The blocking camera skill replaces it
        # with the actual visual answer, preventing an unsupported LLM denial
        # or a delayed "let me look" immediately before the result.
        "reply": "",
        "function_calls": [{
            "function": "capture_camera_view",
            "parameters": {"query": user_text},
        }],
        "new_memories": [],
    }
    queue_message("INFO: Routing explicit vision request directly to camera analysis")

# === Threads ===
def start_bt_controller_thread():
    """
    Wrapper to start the BT Controller functionality in a thread.
    """
    config = load_config()
    if not config['CONTROLS'].get('enabled', False):
        return
    if start_controls is None:
        queue_message("WARNING: BT Controller not available")
        return
    try:
        queue_message(f"LOAD: Starting BT Controller thread...")
        while not stop_event.is_set():
            start_controls()
    except Exception as e:
        queue_message(f"ERROR: {e}")

# === Callback Functions ===

def wake_word_callback(wake_response):
    """
    Play initial response when wake word is detected.

    Parameters:
    - wake_response (str): The response to the wake word.
    """ 

    # User is talking to the device — set route to voice
    try:
        from modules.module_router import set_active_route
        set_active_route("voice")
    except Exception:
        pass

    # Deactivate screensaver when wake word is detected
    if ui_manager:
        ui_manager.deactivate_screensaver()
        character_name = CONFIG['CHAR']['character_name']
        ui_manager.update_data(character_name, wake_response, character_name)

    set_tars_state(TarsState.TALKING)

    # Don't run barge-in on wake responses — they're too short and the mic
    # picks up TARS's own voice, causing false positives
    asyncio.run(play_audio_chunks(wake_response, CONFIG['TTS']['ttsoption'], True))

    set_tars_state(TarsState.LISTENING)

def utterance_callback(message):
    """
    Process the recognized message from STTManager and stream audio response to speakers.

    Parameters:
    - message (str): The recognized message from the Speech-to-Text (STT) module.
    """

    try:
        import modules.module_speed as speed
        import modules.module_llm as llm_mod
        speed.mark_utterance_start()
        speed.start('total')

        # Deactivate screensaver when user speaks
        if ui_manager:
            ui_manager.deactivate_screensaver()

        # Parse the user message
        message_dict = json.loads(message)
        if not message_dict.get('text'):
            return

        user_text = message_dict['text'].strip()
        _route_direct_camera_request(message_dict, user_text)

        # Kick off memory embedding in background so it's ready by prompt-build time
        if memory_manager and memory_manager.long_mem_use and hasattr(memory_manager, 'prefetch_embedding'):
            memory_manager.prefetch_embedding(user_text)

        # Speaker ID: non-blocking at this stage. We record the start time and
        # defer the blocking wait to build_prompt (right before speaker context),
        # giving the background observer maximum time to finish identification.
        _sid_start = time.perf_counter()
        # Use last known named speaker for immediate UI display while the
        # current utterance's speaker ID is still processing in the background.
        _speaker_display = CONFIG['CHAR'].get('user_name', 'User')
        try:
            from modules.module_speaker_id import get_speaker_id_manager
            _sid_mgr = get_speaker_id_manager()
            if _sid_mgr and _sid_mgr.enabled:
                _last = _sid_mgr.get_last_named_speaker()
                if _last:
                    _speaker_display = _last
        except Exception:
            pass

        if ui_manager:
            ui_manager.update_data(_speaker_display, user_text, _speaker_display)

        # Check once if user is on webui — used to gate all webui emissions
        try:
            from modules.module_router import get_active_route
            _is_webui = get_active_route().get("source") == "webui"
        except Exception:
            _is_webui = False

        # Push voice-mode user message to web UI (only if user is on webui)
        if _is_webui:
            try:
                from modules.module_chatui import push_user_message
                push_user_message(user_text, speaker_name=_speaker_display)
            except Exception:
                pass

        if "shutdown pc" in user_text.lower():
            queue_message(f"SHUTDOWN: Shutting down the PC...")
            import subprocess
            subprocess.run(['shutdown', '/s', '/t', '0'], check=False)
            return

        set_tars_state(TarsState.THINKING)

        # ── Sentence-pipeline TTS ─────────────────────────────────────────────
        _acc_raw    = ['']   # cumulative raw text from LLM (may include <think>)
        _clean_seen = ['']   # total clean text processed so far (for delta tracking)

        def _apply_sanitize(text):
            text = _sanitize_for_tts(text)
            text = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', text)
            return text.strip()

        def _on_first_play():
            set_tars_state(TarsState.TALKING)
            if stt_manager:
                stt_manager.start_bargein_monitor(tts_text="")

        pipeline = SentenceTTSPipeline(
            CONFIG['TTS']['ttsoption'],
            sanitize=_apply_sanitize,
            on_first_play=_on_first_play,
        )

        # Add placeholder message to OpenGL UI for streaming updates
        character_name = CONFIG['CHAR']['character_name']
        if ui_manager:
            ui_manager.update_data(character_name, "", character_name)

        def on_reply_chunk(chunk, is_first):
            """Called from LLM streaming thread with each reply text piece."""
            _acc_raw[0] += chunk

            # Remove any completed <think>…</think> blocks from full raw text
            clean_total = re.sub(r'<think>.*?</think>', '', _acc_raw[0], flags=re.DOTALL)

            # If an unclosed <think> tag remains, wait for it to close
            if '<think>' in clean_total:
                return

            # Delta: only the NEW visible text since last call
            new_clean = clean_total[len(_clean_seen[0]):]
            _clean_seen[0] = clean_total

            if not new_clean:
                return

            # Stream to OpenGL UI (update last message in-place)
            if ui_manager:
                ui_manager.update_streaming_data(clean_total)

            # Stream new text to web UI (only if user is on webui)
            if _is_webui:
                try:
                    from modules.module_chatui import stream_reply_token
                    stream_reply_token(new_clean)
                except Exception:
                    pass

            # Update barge-in monitor with latest TTS text (streaming mode)
            if stt_manager:
                stt_manager.update_bargein_tts_text(clean_total)

            # Feed to sentence-pipeline TTS
            pipeline.feed(new_clean)

        # Check if preemptive LLM already fired during silence detection
        preemptive = message_dict.get("preemptive_llm_result")

        stt_to_llm_dur = 0
        if preemptive is not None:
            # Preemptive result: no streaming possible, fall through to normal TTS
            parsed = preemptive
            llm_total_dur = 0.0
        else:
            # Notify web UI that streaming is starting
            try:
                from modules.module_chatui import begin_bot_stream
                begin_bot_stream()
            except Exception:
                pass

            pipeline.start()
            llm_mod._reply_chunk_callback = on_reply_chunk

            # Pass speaker ID start time so the deferred wait happens in
            # build_prompt (before speaker context and memory retrieval).
            llm_mod._sid_start_time = _sid_start

            try:
                stt_to_llm_dur = speed.stop('stt_to_llm')
                speed.start('llm_total')
                parsed = process_completion(user_text)
                llm_total_dur = speed.stop('llm_total')
                # Refresh UI display name now that speaker ID has resolved
                try:
                    from modules.module_prompt import _get_active_user_name
                    _resolved = _get_active_user_name(_speaker_display)
                    if _resolved != _speaker_display:
                        old_speaker = _speaker_display
                        _speaker_display = _resolved
                        if ui_manager:
                            ui_manager.update_message_speaker(old_speaker, user_text, _speaker_display)
                except Exception:
                    pass
            finally:
                llm_mod._reply_chunk_callback = None
                # Flush remaining — try pipeline remainder, fall back to raw
                remaining = pipeline.remainder.strip()
                if not remaining:
                    full_clean = re.sub(r'<think>.*?</think>', '', _acc_raw[0], flags=re.DOTALL).strip()
                    remaining = full_clean[len(_clean_seen[0]):].strip()
                pipeline.finish(remaining=_apply_sanitize(remaining) if remaining else None)

        if parsed is None:
            queue_message("DEBUG VOICE: parsed is None — LLM returned no response")
            if preemptive is None:
                pipeline.finish()
                pipeline.join(timeout=5)
                if stt_manager:
                    stt_manager.stop_bargein_monitor()
                try:
                    if _is_webui:
                        from modules.module_chatui import socketio
                        socketio.emit('bot_message', {'message': ''})
                except Exception:
                    pass
            set_tars_state(TarsState.LISTENING)
            return

        # Extract the final reply text for post-processing (emotion, display)
        if isinstance(parsed, str):
            reply = parsed
        else:
            reply = _sanitize_for_tts(parsed.get("reply", ""))

        try:
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        except Exception:
            pass

        # Detect emotion (parallel-safe — runs while TTS thread plays sentences)
        speed.start('emotion')
        emotion = None
        emotion_raw = None
        axis_scores = {}
        if CONFIG['EMOTION']['enabled'] and user_text:
            _emo_method = CONFIG['EMOTION'].get('emotion_method', 'classifier')
            if _emo_method == 'llm':
                if isinstance(parsed, dict):
                    emotion, emotion_raw, axis_scores = detect_emotion_from_llm(parsed.get('emotion'))
                # else: LLM response wasn't valid JSON — skip emotion silently
            else:
                emotion, emotion_raw, axis_scores = detect_emotion(user_text)
            if emotion:
                try:
                    from modules.module_chatui import update_emotion
                    update_emotion(emotion)
                except Exception:
                    pass
                # Update pipeline so remaining sentences use the detected emotion
                pipeline.set_emotion(emotion)
        emo_dur = speed.stop('emotion')

        # Log interaction for dashboard analytics
        try:
            from modules.module_dashboard_data import log_interaction
            _speaker = None
            try:
                from modules.module_identity import get_identity_manager
                im = get_identity_manager()
                if im:
                    _speaker = im.get_current_speaker()
            except Exception:
                pass
            log_interaction(user_text, reply, emotion=emotion, emotion_raw=emotion_raw, axis_scores=axis_scores, speaker=_speaker, llm_response=parsed)
        except Exception:
            pass

        # Finalize the streaming message with the complete reply
        if ui_manager:
            ui_manager.update_streaming_data(reply)

        # Handle side effects (vision/search/photo run inline, others in background)
        _followup_reply = None
        tools_dur = 0
        if not isinstance(parsed, str):
            func_calls = parsed.get("function_calls", [])
            new_mems = parsed.get("new_memories", [])
            queue_message(f"DEBUG VOICE: parsed type={type(parsed).__name__}, func_calls={func_calls}, new_memories={new_mems}")
            # Check if any called skill is blocking (double-pass: placeholder → result)
            from modules.module_skills import get_skill_manager
            _sm = get_skill_manager()
            def _is_blocking(func_name):
                if _sm:
                    meta = _sm._skill_meta.get(func_name, {})
                    return meta.get("followup", False)
                return False
            has_blocking_tool = any(_is_blocking(fc.get("function", "")) for fc in func_calls)
            if has_blocking_tool:
                queue_message(f"DEBUG VOICE: Running blocking side effects inline")
                speed.start('tools')
                llm_execute_side_effects(parsed, user_text)
                tools_dur = speed.stop('tools')
                # Check if side effects updated the reply (e.g. vision result, search summary)
                updated_reply_raw = parsed.get("reply", "") or ""
                # Compare the text in the same form that TTS receives. The
                # sanitizer normalizes typographic apostrophes, dashes, and
                # other speech punctuation. Comparing the raw LLM text against
                # that normalized text falsely classified an unchanged reply
                # as a second follow-up and spoke it twice.
                updated_reply = _sanitize_for_tts(updated_reply_raw)
                try:
                    updated_reply = re.sub(
                        r"<think>.*?</think>",
                        "",
                        updated_reply,
                        flags=re.DOTALL,
                    ).strip()
                except Exception:
                    pass
                if updated_reply and updated_reply != reply:
                    _followup_reply = updated_reply
                    queue_message(f"DEBUG VOICE: Follow-up reply detected: {_followup_reply[:80]}...")
                else:
                    queue_message(f"DEBUG VOICE: No reply change after side effects")
            elif func_calls or new_mems:
                queue_message(f"DEBUG VOICE: Running side effects in background thread")
                threading.Thread(
                    target=llm_execute_side_effects,
                    args=(parsed, user_text), daemon=True
                ).start()
            else:
                queue_message(f"DEBUG VOICE: No side effects to run")
        else:
            queue_message(f"DEBUG VOICE: parsed is str (legacy), no side effects")

        # For preemptive results, TTS hasn't started yet — play full reply normally
        if preemptive is not None:
            reply_clean = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', reply)
            set_tars_state(TarsState.TALKING)
            if stt_manager:
                stt_manager.start_bargein_monitor(tts_text=reply_clean)
            speed.start('tts')
            was_interrupted = asyncio.run(play_audio_chunks(reply_clean, CONFIG['TTS']['ttsoption'], emotion=emotion))
            pipeline._duration = speed.stop('tts')
            if stt_manager:
                stt_manager.stop_bargein_monitor()
        else:
            # Wait for the sentence-pipeline TTS to finish
            pipeline.join(timeout=120)
            if stt_manager:
                stt_manager.stop_bargein_monitor()
            was_interrupted = pipeline.interrupted

        # Speak follow-up if side effects produced new content (vision result, search summary)
        queue_message(f"DEBUG VOICE: followup_reply={'yes' if _followup_reply else 'no'}, was_interrupted={was_interrupted}")
        followup_tts_dur = 0
        if _followup_reply and not was_interrupted:
            followup_clean = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', _followup_reply)
            # Update OpenGL UI with follow-up content
            set_tars_state(TarsState.TALKING)
            if ui_manager:
                ui_manager.update_streaming_data(_followup_reply)
            if stt_manager:
                stt_manager.start_bargein_monitor(tts_text=followup_clean)
            speed.start('followup_tts')
            was_interrupted = asyncio.run(play_audio_chunks(followup_clean, CONFIG['TTS']['ttsoption'], emotion=emotion))
            followup_tts_dur = speed.stop('followup_tts')
            if stt_manager:
                stt_manager.stop_bargein_monitor()
            reply = _followup_reply  # Update for web UI display

        # After response finishes, return to LISTENING (waiting for next utterance in session)
        # Bot only goes to STANDBY after timeout in STT manager
        if was_interrupted:
            time.sleep(0.3)
        set_tars_state(TarsState.LISTENING)

        # Push final reply to web UI (only if user is on webui)
        try:
            if _is_webui:
                from modules.module_chatui import socketio
                socketio.emit('bot_message', {'message': reply, 'audio_streamed': True})
                socketio.emit('bot_audio_done', {})
                socketio.emit('talking_state', {'talking': False})
        except Exception:
            pass

        # Round summary log — wait for background speaker ID to finish first
        speaker = '?'
        try:
            from modules.module_speaker_id import get_speaker_id_manager
            sid = get_speaker_id_manager()
            if sid:
                sid.wait_for_identification(timeout=2.0)
                spk = sid.get_current_speaker()
                if spk:
                    speaker = spk
        except Exception:
            pass

        # If speaker ID resolved late (after initial display), update WebUI speaker name
        _final_speaker = speaker if (speaker and speaker != '?' and not speaker.startswith("Unknown")) else _speaker_display
        if _final_speaker != _speaker_display:
            try:
                from modules.module_chatui import socketio
                socketio.emit('update_last_user_speaker', {'speaker': _final_speaker})
            except Exception:
                pass

        parts = [
            f"speaker={speaker}",
            f"emotion={emotion or '?'}",
            f"preemptive={'yes' if preemptive is not None else 'no'}",
            f"end={'barge-in' if was_interrupted else 'timeout'}",
        ]
        queue_message(f"ROUND: {' | '.join(parts)}")

        # Speed profiling summary
        total_dur = speed.stop('total')
        if speed.enabled:
            sp = []
            if stt_to_llm_dur:
                sp.append(f"stt_to_llm({speed.fmt(stt_to_llm_dur)})")
            llm_timings = parsed.get('_timings', {}) if isinstance(parsed, dict) else {}
            if llm_timings:
                id_t = llm_timings.get('prompt_identity', 0)
                mem_t = llm_timings.get('prompt_memory', 0)
                prompt_t = llm_timings.get('prompt_build', 0)
                prompt_other = prompt_t - id_t - mem_t
                llm_first_byte = llm_timings.get('llm_first_byte', 0)
                ttft = prompt_t + llm_first_byte
                llm_stream_dur = llm_timings.get('llm_stream', 0)
                token_count = llm_timings.get('token_count', 0)
                parse_dur = llm_timings.get('parse', 0)
                # Top-level: llm_ttft (prompt build→first LLM byte)
                sp.append(f"llm_ttft({speed.fmt(ttft)})")
                # Breakdown: identity, memory, other prompt, network wait
                ttft_parts = [f"identity={speed.fmt(id_t)}", f"memory={speed.fmt(mem_t)}"]
                if prompt_other > 0.001:
                    ttft_parts.append(f"prompt_other={speed.fmt(prompt_other)}")
                ttft_parts.append(f"llm_wait={speed.fmt(llm_first_byte)}")
                sp.append(f"  [{', '.join(ttft_parts)}]")
                # LLM streaming + parse
                if token_count and llm_stream_dur > 0:
                    tps = token_count / llm_stream_dur
                    sp.append(f"llm_stream({speed.fmt(llm_stream_dur)}, {token_count}tok, {tps:.1f} t/s)")
                else:
                    sp.append(f"llm_stream({speed.fmt(llm_stream_dur)})")
                sp.append(f"llm_parse({speed.fmt(parse_dur)})")
            else:
                sp.append(f"llm_total({speed.fmt(llm_total_dur)})")
            sp.append(f"emotion({speed.fmt(emo_dur)})")
            # TTS: show actual playback time; for streaming mode also show wall time
            if preemptive is not None:
                sp.append(f"tts({speed.fmt(pipeline.duration)})")
            else:
                sp.append(f"tts_play({speed.fmt(pipeline.play_time)})")
            if tools_dur:
                sp.append(f"tools({speed.fmt(tools_dur)})")
            if followup_tts_dur:
                sp.append(f"followup_tts({speed.fmt(followup_tts_dur)})")
            sp.append(f"total({speed.fmt(total_dur)})")
            queue_message(f"SPEED: {', '.join(sp)}")

    except json.JSONDecodeError:
        queue_message("ERROR: Invalid JSON format. Could not process user message.")
    except Exception as e:
        set_tars_state(TarsState.LISTENING)
        queue_message(f"ERROR: {e}")

def post_utterance_callback():
    """
    Tell STT whether to keep the current conversation listening.

    STT owns the iterative recording loop. This callback must not call back
    into _transcribe_utterance(), otherwise every conversational turn nests
    another recording call and state cleanup becomes unreliable.
    """
    # Check if radio is active — if so, go back to wake word mode
    try:
        from skills.skill_tars_radio import _radio_thread, _radio_cancel
        if _radio_thread is not None and _radio_thread.is_alive() and not _radio_cancel.is_set():
            queue_message("DEBUG: post_utterance_callback -> radio active, returning to wake word loop")
            set_tars_state(TarsState.STANDBY)
            return False
    except Exception:
        pass

    queue_message("DEBUG: post_utterance_callback -> continuing conversation")
    return True

# === Initialization ===
def initialize_managers(mem_manager, char_manager, stt_mgr, ui_mgr, shutdown_evt=None, battery_mod=None):
    """
    Pass in the shared instances for MemoryManager, CharacterManager, STTManager, and other components.
    
    Parameters:
    - mem_manager: The MemoryManager instance from app.py.
    - char_manager: The CharacterManager instance from app.py.
    - stt_mgr: The STTManager instance from app.py.
    - ui_mgr: The native Qt/QML UI controller from app.py.
    - shutdown_evt: The shutdown event from app.py.
    - battery_mod: The BatteryModule instance from app.py.
    """
    global memory_manager, character_manager, stt_manager, ui_manager, shutdown_event, battery_module
    memory_manager = mem_manager
    character_manager = char_manager
    stt_manager = stt_mgr
    ui_manager = ui_mgr
    shutdown_event = shutdown_evt
    battery_module = battery_mod

def startup_initialization():
    servos_ready = False
    controls = CONFIG.get("CONTROLS", {})
    movement_configured = bool(
        controls.get("enabled", False) or controls.get("voicemovement", False)
    )
    try:
        queue_message("SYSTEM: Starting servo initialization...")
        servos_ready = bool(initialize_servos())
        if servos_ready:
            queue_message("SYSTEM: Servo initialization complete")
        elif not movement_configured:
            queue_message("SYSTEM: Servo initialization skipped; movement is disabled")
        else:
            queue_message(
                "ERROR: Servo startup readiness check failed; the next movement "
                "command will attempt controller recovery"
            )
        try:
            from modules.module_cputemp import (
                CPUTempModule,
                set_cpu_temp_instance, 
                set_ventilate_callback, 
                start_thermal_monitoring
            )
            from modules.module_servoctl import ventilate_on
            cpu_temp_module = CPUTempModule()
            set_cpu_temp_instance(cpu_temp_module)
            set_ventilate_callback(ventilate_on)
            start_thermal_monitoring()
        except Exception as e:
            print(f"WARNING: Thermal monitoring not available: {e}")
    except Exception as e:
        queue_message(f"ERROR: Servo initialization failed - {e}")
        servos_ready = False
    return servos_ready
