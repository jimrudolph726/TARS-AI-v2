"""
module_tts.py

Text-to-Speech (TTS) module for TARS-AI application.

Handles TTS functionality to convert text into audio using:
- Local tools (e.g., espeak-ng)
- Server-based TTS systems

"""


import requests
import os
import time
import threading
from datetime import datetime
import numpy as np
import sounddevice as sd
import soundfile as sf
from io import BytesIO
import asyncio
from dataclasses import dataclass

from modules.module_messageQue import queue_message
from modules.module_config import load_config

CONFIG = load_config()


@dataclass(frozen=True)
class PlaybackResult:
    """Outcome of one TTS request.

    ``bool(result)`` intentionally preserves the historical meaning of
    play_audio_chunks(): True means playback was interrupted.
    """

    interrupted: bool = False
    audio_played: bool = False
    error: str = ""

    def __bool__(self):
        return self.interrupted

# Barge-in: TTS cancellation event (thread-safe)
_tts_cancel_event = threading.Event()
_tts_playing = threading.Event()  # Set while sd.play() is actively outputting audio
_tts_needs_flush = threading.Event()  # Set after TTS finishes; cleared by STT after flushing

# Output device discovery — resolved once on first playback
_output_device = None
_output_device_resolved = False


def _resolve_output_device():
    """Find and cache the audio output device. Runs once, no-op after.

    Prefers real hardware (USB audio, headphones, I2S DACs) over virtual
    ALSA devices like 'default' or 'dmix' which may route to HDMI/null.
    """
    global _output_device, _output_device_resolved
    if _output_device_resolved:
        return

    _output_device_resolved = True

    try:
        devices = sd.query_devices()
    except Exception:
        queue_message("WARNING: Could not query audio devices — using system default")
        _output_device = None
        return

    # Categorize output devices by priority
    usb_devices = []      # USB audio — most likely the external speaker
    hw_devices = []       # Hardware devices (headphones, I2S DACs, bcm2835)
    virtual_devices = []  # Virtual/default ALSA devices

    for i, dev in enumerate(devices):
        if dev.get("max_output_channels", 0) < 1:
            continue
        name = dev.get("name", "").lower()
        # Skip HDMI outputs — they typically don't support standard PCM formats
        if "hdmi" in name:
            continue
        if "usb" in name:
            usb_devices.append((i, dev))
        elif "default" in name or "dmix" in name or "pulse" in name or "sysdefault" in name:
            virtual_devices.append((i, dev))
        else:
            hw_devices.append((i, dev))

    # Pick best device: USB > hardware > virtual
    for label, candidates in [("USB", usb_devices), ("hardware", hw_devices), ("virtual", virtual_devices)]:
        if candidates:
            idx, dev = candidates[0]
            _output_device = idx
            queue_message(f"INFO: Audio output: {dev['name']} (device {idx}, {label})")
            return

    queue_message("WARNING: No audio output device found — using system default")
    _output_device = None


def init_audio_output():
    """Resolve and log the audio output device at startup."""
    _resolve_output_device()


def stop_tts_playback():
    """Signal TTS to stop immediately. Safe to call from any thread."""
    _tts_cancel_event.set()
    try:
        sd.stop()
    except Exception:
        pass

def is_tts_playing():
    """Check if TTS audio is currently being output. Used by barge-in monitor."""
    return _tts_playing.is_set()

def needs_mic_flush():
    """Check and clear the flush flag. Returns True once after each TTS playback."""
    return _tts_needs_flush.is_set()

def clear_mic_flush():
    """Clear the flush flag after STT has flushed the mic buffer."""
    _tts_needs_flush.clear()

# Conditional TTS module imports - not all are available on all devices
text_to_speech_with_pipelining_piper = None
text_to_speech_with_pipelining_silero = None
text_to_speech_with_pipelining_espeak = None
text_to_speech_with_pipelining_elevenlabs = None
text_to_speech_with_pipelining_openai = None
try:
    from modules.module_piper import text_to_speech_with_pipelining_piper as _piper
    text_to_speech_with_pipelining_piper = _piper
except Exception as e:
    queue_message(f"[TTS] Piper module failed to load: {e}")
    pass

try:
    from modules.module_silero import text_to_speech_with_pipelining_silero as _silero
    text_to_speech_with_pipelining_silero = _silero
except ImportError:
    pass

try:
    from modules.module_espeak import text_to_speech_with_pipelining_espeak as _espeak
    text_to_speech_with_pipelining_espeak = _espeak
except ImportError:
    pass

try:
    from modules.module_elevenlabs import text_to_speech_with_pipelining_elevenlabs as _elevenlabs
    text_to_speech_with_pipelining_elevenlabs = _elevenlabs
except ImportError:
    pass

try:
    from modules.module_openai import text_to_speech_with_pipelining_openai as _openai
    text_to_speech_with_pipelining_openai = _openai
except ImportError:
    pass


def update_tts_settings(ttsurl):
    url = f"{ttsurl}/set_tts_settings"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    payload = {
        "stream_chunk_size": 100,
        "temperature": 0.75,
        "speed": 1,
        "length_penalty": 1.0,
        "repetition_penalty": 5,
        "top_p": 0.85,
        "top_k": 50,
        "enable_text_splitting": True
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            queue_message(f"LOAD: TTS Settings updated successfully.")
        else:
            queue_message(f"ERROR: Failed to update TTS settings. Status code: {response.status_code}")
            queue_message(f"INFO: Response: {response.text}")
    except Exception as e:
        queue_message(f"ERROR: TTS update failed: {e}")

def play_audio_stream(tts_stream, samplerate=22050, channels=1, gain=1.0, normalize=False):
    _resolve_output_device()
    try:
        target_rate = 16000
        with sd.OutputStream(samplerate=target_rate, channels=channels, dtype='int16', blocksize=4096, device=_output_device) as stream:
            for chunk in tts_stream:
                if chunk:
                    audio_data = np.frombuffer(chunk, dtype='int16')

                    # Resample to 16kHz if needed
                    if samplerate != target_rate and samplerate > 0:
                        ratio = target_rate / samplerate
                        new_len = int(len(audio_data) * ratio)
                        indices = np.linspace(0, len(audio_data) - 1, new_len)
                        audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data.astype(np.float32)).astype('int16')

                    if normalize:
                        max_value = np.max(np.abs(audio_data))
                        if max_value > 0:
                            audio_data = audio_data / max_value * 32767

                    audio_data = np.clip(audio_data * gain, -32768, 32767).astype('int16')
                    stream.write(audio_data)
                else:
                    queue_message(f"ERROR: Received empty chunk.")
    except Exception as e:
        queue_message(f"ERROR: Error during audio playback: {e}")


async def generate_tts_audio(text, ttsoption, is_wakeword=False, ttsurl=None, toggle_charvoice=True, tts_voice=None, emotion=None):
    try:
        if ttsoption == "espeak" and text_to_speech_with_pipelining_espeak:
            async for chunk in text_to_speech_with_pipelining_espeak(text):
                yield chunk

        elif ttsoption == "piper" and text_to_speech_with_pipelining_piper:
            async for chunk in text_to_speech_with_pipelining_piper(text, emotion=emotion):
                yield chunk

        elif ttsoption == "elevenlabs" and text_to_speech_with_pipelining_elevenlabs:
            async for chunk in text_to_speech_with_pipelining_elevenlabs(text, is_wakeword):
                yield chunk

        elif ttsoption == "silero" and text_to_speech_with_pipelining_silero:
            async for chunk in text_to_speech_with_pipelining_silero(text):
                yield chunk 

        elif ttsoption == "openai" and text_to_speech_with_pipelining_openai:
            async for chunk in text_to_speech_with_pipelining_openai(text, is_wakeword):
                yield chunk

        elif ttsoption == "external":
            external_url = (CONFIG["TTS"].ttsurl or "").rstrip("/")
            if not external_url:
                queue_message("ERROR: External TTS URL (ttsurl) is not configured")
                return
            payload = {"text": text}
            ext_voice = CONFIG["TTS"].tts_voice or ""
            if ext_voice:
                payload["voice"] = ext_voice
            headers = {"Content-Type": "application/json"}
            api_key = os.environ.get('EXTERNAL_API_KEY', '')
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            try:
                response = requests.post(f"{external_url}/tts/generate", json=payload, headers=headers, timeout=30)
                if response.status_code == 200:
                    audio_buffer = BytesIO(response.content)
                    audio_buffer.seek(0)
                    yield audio_buffer
                else:
                    queue_message(f"ERROR: External TTS server returned {response.status_code}")
            except requests.exceptions.ConnectionError:
                queue_message(f"ERROR: Cannot connect to external TTS server at {external_url}")
            except Exception as e:
                queue_message(f"ERROR: External TTS failed: {e}")

        else:
            # Try fallback TTS options
            fallback_order = [
                ("openai", text_to_speech_with_pipelining_openai),
                ("elevenlabs", text_to_speech_with_pipelining_elevenlabs),
                ("espeak", text_to_speech_with_pipelining_espeak),
                ("piper", text_to_speech_with_pipelining_piper),
            ]
            
            for name, func in fallback_order:
                if func is not None:
                    queue_message(f"WARNING: TTS '{ttsoption}' not available, falling back to '{name}'")
                    if name in ["openai", "elevenlabs"]:
                        async for chunk in func(text, is_wakeword):
                            yield chunk
                    else:
                        async for chunk in func(text):
                            yield chunk
                    return
            
            queue_message(f"ERROR: No TTS backend available for '{ttsoption}'")

    except Exception as e:
        queue_message(f"ERROR: Text-to-speech generation failed: {e}")

import re as _re
import queue as _queue


class SentenceTTSPipeline:
    """Sentence-by-sentence TTS pipeline.

    Accepts streamed text via feed(), splits at sentence boundaries,
    and plays each sentence through TTS as soon as it's complete.
    TTS plays sentence 1 while the LLM is still generating sentence 2.

    Usage:
        pipeline = SentenceTTSPipeline('piper', sanitize=my_func, on_first_play=cb)
        pipeline.start()
        pipeline.feed("Hello there! How are ")
        pipeline.feed("you doing today?")
        pipeline.finish()
        pipeline.join()
        print(pipeline.interrupted, pipeline.duration)
    """

    _SENT_RE = _re.compile(r'(?<=[.!?])\s+')
    _CLAUSE_RE = _re.compile(r'(?<=[.!?;:,])\s+')
    _MIN_SENT = 20
    _MIN_CLAUSE = 12      # ~3 words; first chunk only for lower latency

    def __init__(self, tts_option, sanitize=None, on_first_play=None, play_func=None):
        self._tts_option = tts_option
        self._sanitize = sanitize or str.strip
        self._on_first_play = on_first_play
        # Custom async play function: async def(sentence, tts_option) -> bool (interrupted).
        # When None, defaults to play_audio_chunks (device speaker).
        self._play_func = play_func
        self._queue = _queue.Queue()
        self._remainder = ''
        self._first_queued = False
        self._interrupted = False
        self._audio_played = False
        self._failed_sentences = 0
        self._duration = 0.0
        self._play_time = 0.0   # Actual TTS synthesis+playback time (excludes queue waits)
        self._thread = None
        self._emotion = None    # Set via set_emotion() once detected

    def start(self):
        """Start the TTS worker thread."""
        self._thread = threading.Thread(target=self._worker, daemon=True, name="tts-pipeline")
        self._thread.start()

    def set_emotion(self, emotion):
        """Set the emotion for multispeaker TTS. Can be called while pipeline is running."""
        self._emotion = emotion

    def feed(self, text):
        """Feed visible text. Complete sentences are queued for TTS immediately."""
        self._remainder = self._extract_sentences(self._remainder + text)

    def finish(self, remaining=None):
        """Flush remaining text and signal end of stream.

        If remaining is provided, it replaces the internal remainder
        (useful for fallback flush from raw LLM output).
        """
        text = remaining if remaining is not None else self._remainder
        text = self._sanitize(text) if text else ''
        if text:
            self._queue.put(text)
        self._remainder = ''
        self._queue.put(None)

    def join(self, timeout=120):
        """Wait for TTS worker to finish playing all sentences."""
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                queue_message(f"ERROR: TTS pipeline did not finish within {timeout} seconds")
                self._interrupted = True
                stop_tts_playback()
                self._thread.join(timeout=3)

    @property
    def remainder(self):
        """Current un-flushed text (no complete sentence boundary yet)."""
        return self._remainder

    @property
    def interrupted(self):
        return self._interrupted

    @property
    def audio_played(self):
        """Whether at least one audio chunk reached the speaker."""
        return self._audio_played

    @property
    def failed_sentences(self):
        return self._failed_sentences

    @property
    def duration(self):
        return self._duration

    @property
    def play_time(self):
        """Actual TTS synthesis+playback time (excludes queue wait time)."""
        return self._play_time

    def _extract_sentences(self, text):
        """Split text at boundaries, queue complete chunks, return remainder.

        First chunk splits at clause boundaries (,;:) with a shorter
        threshold for lower initial latency.  Subsequent chunks use full
        sentence boundaries (.!?) for better prosody.
        """
        while True:
            pos = 0
            m = None
            if self._first_queued:
                # Sentence boundaries for subsequent chunks
                while True:
                    m = self._SENT_RE.search(text, pos)
                    if not m or m.start() >= self._MIN_SENT:
                        break
                    pos = m.end()
            else:
                # Clause boundaries for first chunk (lower latency)
                while True:
                    m = self._CLAUSE_RE.search(text, pos)
                    if not m or m.start() >= self._MIN_CLAUSE:
                        break
                    pos = m.end()
            if not m:
                break
            sentence = self._sanitize(text[:m.start() + 1])
            text = text[m.end():]
            if sentence:
                self._queue.put(sentence)
                if not self._first_queued:
                    self._first_queued = True
        return text

    def _worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        t_start = time.perf_counter()
        play_total = 0.0
        first = True

        def _mark_first_audio():
            nonlocal first
            if not first:
                return
            first = False
            if self._on_first_play:
                try:
                    self._on_first_play()
                except Exception:
                    pass

        try:
            while not self._interrupted:
                # Wait for either a sentence or the finish sentinel.  LLMs can
                # legitimately take more than 30 seconds on a Raspberry Pi;
                # timing out here abandoned TTS while the UI kept streaming
                # the eventual response text.
                sentence = self._queue.get()
                if sentence is None:
                    break
                queue_message(f"DEBUG: TTS speaking: {sentence}")
                t_play = time.perf_counter()
                try:
                    if self._play_func:
                        # Custom players retain the original bool contract.
                        _mark_first_audio()
                        raw_result = loop.run_until_complete(
                            self._play_func(sentence, self._tts_option)
                        )
                        result = raw_result if isinstance(raw_result, PlaybackResult) else PlaybackResult(
                            interrupted=bool(raw_result), audio_played=not bool(raw_result)
                        )
                    else:
                        result = loop.run_until_complete(
                            play_audio_chunks(
                                sentence,
                                self._tts_option,
                                emotion=self._emotion,
                                return_status=True,
                                on_audio_start=_mark_first_audio,
                            )
                        )
                except Exception as e:
                    queue_message(f"ERROR: TTS pipeline failed: {e}")
                    result = PlaybackResult(error=str(e))
                play_total += time.perf_counter() - t_play

                self._audio_played = self._audio_played or result.audio_played
                if not result.audio_played and not result.interrupted:
                    self._failed_sentences += 1
                    queue_message(f"ERROR: TTS produced no playable audio for: {sentence[:80]}")

                if result.interrupted:
                    self._interrupted = True
                    while not self._queue.empty():
                        try:
                            self._queue.get_nowait()
                        except _queue.Empty:
                            break
        finally:
            self._duration = time.perf_counter() - t_start
            self._play_time = play_total
            loop.close()


async def play_audio_chunks(
    text,
    config,
    is_wakeword=False,
    emotion=None,
    return_status=False,
    on_audio_start=None,
    _allow_fallback=True,
):
    """Synthesize and play text, falling back to eSpeak if needed.

    Existing callers receive the historical ``interrupted`` boolean.  The
    sentence pipeline asks for a PlaybackResult so it can distinguish a
    successful response from a backend that silently yielded no audio.
    """
    _resolve_output_device()
    if not is_wakeword:
        queue_message(f"DEBUG: TTS speaking (direct): {text}")
    _tts_cancel_event.clear()
    audio_queue = asyncio.Queue(maxsize=3)
    synthesis_done = asyncio.Event()
    was_interrupted = False
    audio_played = False
    playback_errors = []

    async def synthesize_chunks():
        gen = generate_tts_audio(text, config, is_wakeword, emotion=emotion).__aiter__()
        try:
            async for audio_chunk in gen:
                if _tts_cancel_event.is_set():
                    break
                # Use put_nowait with a wait loop so we can check for cancellation
                while not _tts_cancel_event.is_set():
                    try:
                        audio_queue.put_nowait(audio_chunk)
                        break
                    except asyncio.QueueFull:
                        await asyncio.sleep(0.05)
        except Exception as e:
            queue_message(f"ERROR: Synthesis failed: {e}")
        finally:
            # Explicitly close the async generator so pending HTTP streams
            # (ElevenLabs, OpenAI, etc.) are cleaned up before the event loop closes.
            try:
                await gen.aclose()
            except Exception:
                pass
            synthesis_done.set()

    def _notify_talking_state(endpoint):
        """Fire-and-forget HTTP notification to webui (non-blocking)."""
        try:
            requests.get(f"http://127.0.0.1:{CONFIG['ACCESS'].get('webui_port', 80)}/{endpoint}", timeout=1)
        except Exception:
            pass

    async def play_chunks():
        nonlocal was_interrupted, audio_played
        threading.Thread(target=_notify_talking_state, args=("start_talking",), daemon=True).start()

        try:
            while True:
                if _tts_cancel_event.is_set():
                    was_interrupted = True
                    break

                try:
                    try:
                        audio_chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        if synthesis_done.is_set() and audio_queue.empty():
                            break
                        continue

                    data, samplerate = sf.read(audio_chunk, dtype='float32')
                    if np.size(data) == 0:
                        raise ValueError("TTS backend returned an empty audio chunk")

                    # Resample to 16kHz if needed
                    if samplerate != 16000:
                        ratio = 16000 / samplerate
                        new_len = int(len(data) * ratio)
                        if data.ndim == 1:
                            indices = np.linspace(0, len(data) - 1, new_len)
                            data = np.interp(indices, np.arange(len(data)), data)
                        else:
                            indices = np.linspace(0, len(data) - 1, new_len)
                            data = np.column_stack([
                                np.interp(indices, np.arange(len(data)), data[:, ch])
                                for ch in range(data.shape[1])
                            ])
                        samplerate = 16000

                    max_val = np.max(np.abs(data))
                    if max_val > 0:
                        data = data / max_val

                    gain = 1.5
                    data = np.clip(data * gain, -1.0, 1.0)

                    sd.play(data, samplerate, device=_output_device)
                    _tts_playing.set()
                    if not audio_played:
                        audio_played = True
                        if on_audio_start:
                            try:
                                on_audio_start()
                            except Exception as e:
                                queue_message(f"WARN: TTS start callback failed: {e}")

                    # Log time-to-first-audio on the first chunk
                    import modules.module_speed as speed
                    speed.mark_first_audio()

                    # Poll instead of sd.wait() so we can check for barge-in
                    while True:
                        if _tts_cancel_event.is_set():
                            sd.stop()
                            was_interrupted = True
                            break
                        try:
                            stream = sd.get_stream()
                            if stream is None or not stream.active:
                                break
                        except Exception:
                            break
                        await asyncio.sleep(0.05)

                    _tts_playing.clear()
                    if not is_wakeword:
                        _tts_needs_flush.set()

                    if was_interrupted:
                        break

                    # Brief pause between chunks for barge-in detection.
                    # Monitor checks mic RMS only when _tts_playing is clear.
                    for _ in range(6):  # 300ms window (6 x 50ms)
                        if _tts_cancel_event.is_set():
                            was_interrupted = True
                            break
                        await asyncio.sleep(0.05)

                    if was_interrupted:
                        break

                except Exception as e:
                    playback_errors.append(str(e))
                    queue_message(f"ERROR: Failed to play chunk: {e}")
                    if synthesis_done.is_set() and audio_queue.empty():
                        break
        finally:
            _tts_playing.clear()
            threading.Thread(target=_notify_talking_state, args=("stop_talking",), daemon=True).start()

    try:
        await asyncio.gather(synthesize_chunks(), play_chunks())
    finally:
        _tts_playing.clear()

    # A backend can fail internally and simply yield nothing. Do not report
    # that as a successful spoken response: use the lightweight local voice
    # so the user still hears TARS and log exactly what happened.
    if (not audio_played and not was_interrupted and _allow_fallback
            and config != "espeak" and text_to_speech_with_pipelining_espeak):
        queue_message(f"WARNING: TTS '{config}' produced no audio; retrying with eSpeak")
        return await play_audio_chunks(
            text,
            "espeak",
            is_wakeword=is_wakeword,
            emotion=emotion,
            return_status=return_status,
            on_audio_start=on_audio_start,
            _allow_fallback=False,
        )

    error = "; ".join(playback_errors)
    if not audio_played and not was_interrupted and not error:
        error = f"TTS backend '{config}' produced no audio"
    result = PlaybackResult(was_interrupted, audio_played, error)
    return result if return_status else result.interrupted
