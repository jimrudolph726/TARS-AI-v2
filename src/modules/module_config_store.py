"""Typed configuration parsing and crash-safe persistence for TARS.

The public helpers in this module deliberately use only the Python standard
library so they are available to the main runtime, WebUI, and standalone servo
testers.  ``config.ini`` remains the user-facing format; this module provides a
single place to validate its important values and to replace it atomically.
"""

from __future__ import annotations

import configparser
import json
import os
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Dict, Iterator, Mapping, Optional, Sequence, Tuple


SERVO_MIN_PULSE = 10
SERVO_MAX_PULSE = 600
_MISSING = object()
_LOCKS: Dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class ConfigValidationError(ValueError):
    """Raised when an INI file is syntactically valid but unsafe or malformed."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(str(error) for error in errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class ControlsSettings:
    enabled: bool
    ventilate: bool
    voicemovement: bool
    swap_turn_directions: bool
    invert_y: bool
    controller_name: str


@dataclass(frozen=True)
class AudioSettings:
    input_device: str
    output_device: str


@dataclass(frozen=True)
class CharacterSettings:
    card_path: str
    user_name: str
    user_details: str
    location_name: str
    latitude: Optional[float]
    longitude: Optional[float]
    enable_thinking_responses: bool
    thinking_responses: Tuple[str, ...]
    responses: Tuple[str, ...]


@dataclass(frozen=True)
class STTSettings:
    use_indicators: bool
    stt_processor: str
    language: str
    external_url: str
    openai_model: str
    openai_delay: str
    openai_fallback: str
    wake_word: str
    wake_word_processor: str
    atomik_mode: str
    sensitivity: int
    vad_method: str
    speechdelay: int
    openai_stt_timeout: float
    enable_bargein: bool
    bargein_sensitivity: int
    mic_amp_gain: float
    silence_margin: float
    speaker_id_enabled: bool
    speaker_id_threshold: float
    sherpa_onnx_denoise: bool
    sherpa_onnx_punctuation: bool
    vad_transcript_verify: bool
    vad_presence_gate: str
    vad_speaker_verify: str
    vad_speaker_threshold: float
    bargein_mode: str


@dataclass(frozen=True)
class LLMSettings:
    backend: str
    base_url: str
    openai_model: str
    other_model: str
    grok_model: str
    system_prompt: str
    context_size: int
    max_tokens: int
    seed: int
    temperature: float
    top_p: float
    json_mode: bool
    connect_timeout: float
    read_timeout: float
    total_timeout: float
    max_retries: int
    retry_backoff: float
    override_encoding_model: str


@dataclass(frozen=True)
class VisionSettings:
    enabled: bool
    camera_rotation: int
    processor: str
    use_llm_backend: bool
    base_url: str
    model: str
    max_tokens: int


@dataclass(frozen=True)
class TTSSettings:
    option: str
    toggle_character_voice: bool
    url: str
    voice: str
    elevenlabs_voice_id: str
    elevenlabs_model: str
    openai_voice: str
    piper_multispeaker: bool
    piper_speakers: Mapping[str, int]


@dataclass(frozen=True)
class EmotionSettings:
    enabled: bool
    method: str
    model: str


@dataclass(frozen=True)
class RAGSettings:
    enabled: bool
    enable_topic_tracking: bool
    strategy: str
    context_window: int
    max_memories: int
    top_k: int
    recency_boost_days: int
    embedding_source: str
    embedding_url: str


@dataclass(frozen=True)
class ServoSettings:
    arms_present: bool
    movement_watchdog_enabled: bool
    movement_watchdog_timeout: float
    movement_stall_timeout: float
    left_up_height: int
    left_down_height: int
    perfect_left_height_offset: int
    right_up_height: int
    right_down_height: int
    perfect_right_height_offset: int
    forward_left_leg: int
    back_left_leg: int
    perfect_left_leg_offset: int
    forward_right_leg: int
    back_right_leg: int
    perfect_right_leg_offset: int
    left_main_min: int
    left_main_max: int
    left_main_offset: int
    left_forearm_min: int
    left_forearm_max: int
    left_forearm_offset: int
    left_hand_min: int
    left_hand_max: int
    left_hand_offset: int
    right_main_min: int
    right_main_max: int
    right_main_offset: int
    right_forearm_min: int
    right_forearm_max: int
    right_forearm_offset: int
    right_hand_min: int
    right_hand_max: int
    right_hand_offset: int

    def legacy_dict(self) -> Dict[str, object]:
        """Return the historical key spelling used by existing movement code."""
        return {
            "arms_present": self.arms_present,
            "movement_watchdog_enabled": self.movement_watchdog_enabled,
            "movement_watchdog_timeout": self.movement_watchdog_timeout,
            "movement_stall_timeout": self.movement_stall_timeout,
            "leftUpHeight": self.left_up_height,
            "leftDownHeight": self.left_down_height,
            "perfectLeftHeightOffset": self.perfect_left_height_offset,
            "rightUpHeight": self.right_up_height,
            "rightDownHeight": self.right_down_height,
            "perfectRightHeightOffset": self.perfect_right_height_offset,
            "forwardLeftLeg": self.forward_left_leg,
            "backLeftLeg": self.back_left_leg,
            "perfectLeftLegOffset": self.perfect_left_leg_offset,
            "forwardRightLeg": self.forward_right_leg,
            "backRightLeg": self.back_right_leg,
            "perfectRightLegOffset": self.perfect_right_leg_offset,
            "leftMainMin": self.left_main_min,
            "leftMainMax": self.left_main_max,
            "leftMainOffset": self.left_main_offset,
            "leftForarmMin": self.left_forearm_min,
            "leftForarmMax": self.left_forearm_max,
            "leftForearmOffset": self.left_forearm_offset,
            "leftHandMin": self.left_hand_min,
            "leftHandMax": self.left_hand_max,
            "leftHandOffset": self.left_hand_offset,
            "rightMainMin": self.right_main_min,
            "rightMainMax": self.right_main_max,
            "rightMainOffset": self.right_main_offset,
            "rightForarmMin": self.right_forearm_min,
            "rightForarmMax": self.right_forearm_max,
            "rightForearmOffset": self.right_forearm_offset,
            "rightHandMin": self.right_hand_min,
            "rightHandMax": self.right_hand_max,
            "rightHandOffset": self.right_hand_offset,
        }


@dataclass(frozen=True)
class AccessSettings:
    webui_enabled: bool
    webui_port: int
    webui_password: str
    webui_theme: str
    remote_access_enabled: bool


@dataclass(frozen=True)
class UISettings:
    enabled: bool
    camera_enabled: bool
    show_mouse: bool
    fullscreen: bool
    screen_width: int
    screen_height: int
    rotation: int
    show_time: bool
    show_cpu_temp: bool
    ampm_format: bool
    app: str
    target_fps: int
    font_size: int
    screensaver_timer: int
    screensaver_cycle_interval: int
    screensaver_list: Tuple[str, ...]


@dataclass(frozen=True)
class BatterySettings:
    enabled: bool
    auto_shutdown: bool
    capacity_mah: int
    initial_voltage: float
    cutoff_voltage: float


@dataclass(frozen=True)
class TypedConfig:
    """Immutable, validated view of safety- and runtime-critical settings."""

    source: Path
    controls: ControlsSettings
    audio: AudioSettings
    character: CharacterSettings
    stt: STTSettings
    llm: LLMSettings
    vision: VisionSettings
    tts: TTSSettings
    emotion: EmotionSettings
    rag: RAGSettings
    servo: ServoSettings
    access: AccessSettings
    ui: UISettings
    battery: BatterySettings
    sections: Mapping[str, Mapping[str, str]]


def _new_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(
        interpolation=None,
        strict=True,
        inline_comment_prefixes=("#", ";"),
    )
    return parser


class _Reader:
    def __init__(self, parser: configparser.ConfigParser):
        self.parser = parser
        self.errors = []

    def _raw(self, section: str, option: str, default=_MISSING) -> Optional[str]:
        if not self.parser.has_section(section):
            if default is _MISSING:
                self.errors.append(f"Missing section [{section}]")
                return None
            return str(default)
        if not self.parser.has_option(section, option):
            if default is _MISSING:
                self.errors.append(f"Missing setting [{section}] {option}")
                return None
            return str(default)
        return self.parser.get(section, option, raw=True)

    def string(
        self,
        section: str,
        option: str,
        default=_MISSING,
        choices: Optional[Sequence[str]] = None,
        allow_empty: bool = True,
    ) -> str:
        raw = self._raw(section, option, default)
        value = "" if raw is None else str(raw).strip()
        if not allow_empty and not value:
            self.errors.append(f"[{section}] {option} cannot be empty")
        if choices and value.lower() not in {choice.lower() for choice in choices}:
            self.errors.append(
                f"[{section}] {option} must be one of: {', '.join(choices)}"
            )
        return value

    def boolean(self, section: str, option: str, default=_MISSING) -> bool:
        raw = self._raw(section, option, default)
        if raw is None:
            return False
        normalized = str(raw).strip().lower()
        states = configparser.ConfigParser.BOOLEAN_STATES
        if normalized not in states:
            self.errors.append(f"[{section}] {option} must be true or false")
            return False
        return bool(states[normalized])

    def integer(
        self,
        section: str,
        option: str,
        default=_MISSING,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        choices: Optional[Sequence[int]] = None,
    ) -> int:
        raw = self._raw(section, option, default)
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            self.errors.append(f"[{section}] {option} must be an integer")
            return int(default) if default is not _MISSING else 0
        if minimum is not None and value < minimum:
            self.errors.append(f"[{section}] {option} must be at least {minimum}")
        if maximum is not None and value > maximum:
            self.errors.append(f"[{section}] {option} must be at most {maximum}")
        if choices is not None and value not in choices:
            self.errors.append(
                f"[{section}] {option} must be one of: {', '.join(map(str, choices))}"
            )
        return value

    def number(
        self,
        section: str,
        option: str,
        default=_MISSING,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> float:
        raw = self._raw(section, option, default)
        try:
            value = float(str(raw).strip())
        except (TypeError, ValueError):
            self.errors.append(f"[{section}] {option} must be a number")
            return float(default) if default is not _MISSING else 0.0
        if minimum is not None and value < minimum:
            self.errors.append(f"[{section}] {option} must be at least {minimum:g}")
        if maximum is not None and value > maximum:
            self.errors.append(f"[{section}] {option} must be at most {maximum:g}")
        return value

    def optional_number(
        self,
        section: str,
        option: str,
        default: str = "",
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> Optional[float]:
        raw = self._raw(section, option, default)
        if raw is None or not str(raw).strip():
            return None
        try:
            value = float(str(raw).strip())
        except (TypeError, ValueError):
            self.errors.append(f"[{section}] {option} must be a number or empty")
            return None
        if minimum is not None and value < minimum:
            self.errors.append(f"[{section}] {option} must be at least {minimum:g}")
        if maximum is not None and value > maximum:
            self.errors.append(f"[{section}] {option} must be at most {maximum:g}")
        return value

    def string_list(
        self,
        section: str,
        option: str,
        default: str = "[]",
    ) -> Tuple[str, ...]:
        raw = self._raw(section, option, default)
        try:
            parsed = json.loads(str(raw))
        except (TypeError, json.JSONDecodeError):
            self.errors.append(f"[{section}] {option} must be a JSON list of strings")
            return ()
        if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
            self.errors.append(f"[{section}] {option} must be a JSON list of strings")
            return ()
        return tuple(parsed)


def _read_parser(path: Path) -> configparser.ConfigParser:
    parser = _new_parser()
    try:
        with path.open("r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except FileNotFoundError:
        raise ConfigValidationError([f"Configuration file not found: {path}"])
    except (configparser.Error, UnicodeError, OSError) as exc:
        raise ConfigValidationError([f"Could not parse {path.name}: {exc}"])
    return parser


def _immutable_sections(
    parser: configparser.ConfigParser,
) -> Mapping[str, Mapping[str, str]]:
    sections = {
        section: MappingProxyType(dict(parser.items(section, raw=True)))
        for section in parser.sections()
    }
    return MappingProxyType(sections)


def _validate_servo_targets(reader: _Reader, servo: ServoSettings) -> None:
    targets: Tuple[Tuple[str, int], ...] = (
        ("leftUpHeight + perfectLeftHeightOffset", servo.left_up_height + servo.perfect_left_height_offset),
        ("leftDownHeight + perfectLeftHeightOffset", servo.left_down_height + servo.perfect_left_height_offset),
        ("rightUpHeight - perfectRightHeightOffset", servo.right_up_height - servo.perfect_right_height_offset),
        ("rightDownHeight - perfectRightHeightOffset", servo.right_down_height - servo.perfect_right_height_offset),
        ("forwardLeftLeg + perfectLeftLegOffset", servo.forward_left_leg + servo.perfect_left_leg_offset),
        ("backLeftLeg + perfectLeftLegOffset", servo.back_left_leg + servo.perfect_left_leg_offset),
        ("forwardRightLeg + perfectRightLegOffset", servo.forward_right_leg + servo.perfect_right_leg_offset),
        ("backRightLeg + perfectRightLegOffset", servo.back_right_leg + servo.perfect_right_leg_offset),
        ("leftMainMin + leftMainOffset", servo.left_main_min + servo.left_main_offset),
        ("leftMainMax + leftMainOffset", servo.left_main_max + servo.left_main_offset),
        ("leftForarmMin + leftForearmOffset", servo.left_forearm_min + servo.left_forearm_offset),
        ("leftForarmMax + leftForearmOffset", servo.left_forearm_max + servo.left_forearm_offset),
        ("leftHandMin + leftHandOffset", servo.left_hand_min + servo.left_hand_offset),
        ("leftHandMax + leftHandOffset", servo.left_hand_max + servo.left_hand_offset),
        ("rightMainMin + rightMainOffset", servo.right_main_min + servo.right_main_offset),
        ("rightMainMax + rightMainOffset", servo.right_main_max + servo.right_main_offset),
        ("rightForarmMin + rightForearmOffset", servo.right_forearm_min + servo.right_forearm_offset),
        ("rightForarmMax + rightForearmOffset", servo.right_forearm_max + servo.right_forearm_offset),
        ("rightHandMin + rightHandOffset", servo.right_hand_min + servo.right_hand_offset),
        ("rightHandMax + rightHandOffset", servo.right_hand_max + servo.right_hand_offset),
    )
    for label, value in targets:
        if not SERVO_MIN_PULSE <= value <= SERVO_MAX_PULSE:
            reader.errors.append(
                f"[SERVO] {label} resolves to unsafe PWM value {value}; "
                f"allowed range is {SERVO_MIN_PULSE}-{SERVO_MAX_PULSE}"
            )


def parse_typed_config(
    parser: configparser.ConfigParser,
    source: Path,
) -> TypedConfig:
    """Build an immutable typed snapshot and report all validation errors."""
    r = _Reader(parser)

    controls = ControlsSettings(
        enabled=r.boolean("CONTROLS", "enabled"),
        ventilate=r.boolean("CONTROLS", "ventilate", False),
        voicemovement=r.boolean("CONTROLS", "voicemovement"),
        swap_turn_directions=r.boolean("CONTROLS", "swap_turn_directions", False),
        invert_y=r.boolean("CONTROLS", "invert_y", False),
        controller_name=r.string("CONTROLS", "controller_name", ""),
    )
    audio = AudioSettings(
        input_device=r.string("AUDIO", "input_device", ""),
        output_device=r.string("AUDIO", "output_device", ""),
    )
    character = CharacterSettings(
        card_path=r.string("CHAR", "character_card_path", allow_empty=False),
        user_name=r.string("CHAR", "user_name", ""),
        user_details=r.string("CHAR", "user_details", ""),
        location_name=r.string("CHAR", "location_name", ""),
        latitude=r.optional_number("CHAR", "latitude", "", -90.0, 90.0),
        longitude=r.optional_number("CHAR", "longitude", "", -180.0, 180.0),
        enable_thinking_responses=r.boolean("CHAR", "enable_thinking_responses", True),
        thinking_responses=r.string_list("CHAR", "thinking_responses", "[]"),
        responses=r.string_list("CHAR", "responses", "[]"),
    )
    stt = STTSettings(
        use_indicators=r.boolean("STT", "use_indicators"),
        stt_processor=r.string("STT", "stt_processor", allow_empty=False),
        language=r.string("STT", "language", allow_empty=False),
        external_url=r.string("STT", "external_url", ""),
        openai_model=r.string("STT", "openai_stt_model", "gpt-live-transcribe", allow_empty=False),
        openai_delay=r.string("STT", "openai_stt_delay", "low"),
        openai_fallback=r.string("STT", "openai_stt_fallback", "sherpa-onnx"),
        wake_word=r.string("STT", "wake_word", allow_empty=False),
        wake_word_processor=r.string("STT", "wake_word_processor", allow_empty=False),
        atomik_mode=r.string("STT", "atomik_mode", "auto", ("auto", "model", "template")),
        sensitivity=r.integer("STT", "sensitivity", 7, 1, 10),
        vad_method=r.string("STT", "vad_method", allow_empty=False),
        speechdelay=r.integer("STT", "speechdelay", 15, 0),
        openai_stt_timeout=r.number("STT", "openai_stt_timeout", 12.0, 0.1),
        enable_bargein=r.boolean("STT", "enable_bargein", True),
        bargein_sensitivity=r.integer("STT", "bargein_sensitivity", 5, 1, 10),
        mic_amp_gain=r.number("STT", "mic_amp_gain", 10.0, 0.0),
        silence_margin=r.number("STT", "silence_margin", 3.0, 0.01),
        speaker_id_enabled=r.boolean("STT", "speaker_id_enabled", False),
        speaker_id_threshold=r.number("STT", "speaker_id_threshold", 0.75, 0.0, 1.0),
        sherpa_onnx_denoise=r.boolean("STT", "sherpa_onnx_denoise", False),
        sherpa_onnx_punctuation=r.boolean("STT", "sherpa_onnx_punctuation", False),
        vad_transcript_verify=r.boolean("STT", "vad_transcript_verify", False),
        vad_presence_gate=r.string("STT", "vad_presence_gate", "off"),
        vad_speaker_verify=r.string("STT", "vad_speaker_verify", "off"),
        vad_speaker_threshold=r.number("STT", "vad_speaker_threshold", 0.60, 0.0, 1.0),
        bargein_mode=r.string("STT", "bargein_mode", "fuzzy"),
    )
    llm = LLMSettings(
        backend=r.string("LLM", "llm_backend", allow_empty=False),
        base_url=r.string("LLM", "base_url", ""),
        openai_model=r.string("LLM", "openai_model", ""),
        other_model=r.string("LLM", "other_model", ""),
        grok_model=r.string("LLM", "grok_model", ""),
        system_prompt=r.string("LLM", "systemprompt", ""),
        context_size=r.integer("LLM", "contextsize", minimum=1),
        max_tokens=r.integer("LLM", "max_tokens", minimum=1),
        seed=r.integer("LLM", "seed", -1),
        temperature=r.number("LLM", "temperature", minimum=0.0, maximum=2.0),
        top_p=r.number("LLM", "top_p", minimum=0.0, maximum=1.0),
        json_mode=r.boolean("LLM", "json_mode", True),
        connect_timeout=r.number("LLM", "connect_timeout", 10.0, 0.1),
        read_timeout=r.number("LLM", "read_timeout", 45.0, 0.1),
        total_timeout=r.number("LLM", "total_timeout", 120.0, 0.1),
        max_retries=r.integer("LLM", "max_retries", 1, 0, 10),
        retry_backoff=r.number("LLM", "retry_backoff", 0.5, 0.0),
        override_encoding_model=r.string("LLM", "override_encoding_model", "cl100k_base"),
    )
    if llm.total_timeout < llm.connect_timeout:
        r.errors.append("[LLM] total_timeout cannot be less than connect_timeout")
    if llm.total_timeout < llm.read_timeout:
        r.errors.append("[LLM] total_timeout cannot be less than read_timeout")

    vision = VisionSettings(
        enabled=r.boolean("VISION", "enabled"),
        camera_rotation=r.integer("VISION", "camera_rotation", 0, choices=(0, 90, 180, 270)),
        processor=r.string("VISION", "vision_processor", "blip", allow_empty=False),
        use_llm_backend=r.boolean("VISION", "use_llm_backend", True),
        base_url=r.string("VISION", "base_url", ""),
        model=r.string("VISION", "vision_model", ""),
        max_tokens=r.integer("VISION", "vision_max_tokens", 150, 1),
    )
    piper_speakers = {
        emotion: r.integer("TTS", f"piper_speaker_{emotion}", default)
        for emotion, default in (
            ("joy", 0),
            ("neutral", 1),
            ("fear", 2),
            ("curiosity", 3),
            ("love", 4),
            ("sadness", 5),
            ("surprise", 6),
            ("anger", 7),
        )
    }
    tts = TTSSettings(
        option=r.string("TTS", "ttsoption", allow_empty=False),
        toggle_character_voice=r.boolean("TTS", "toggle_charvoice"),
        url=r.string("TTS", "ttsurl", ""),
        voice=r.string("TTS", "tts_voice", ""),
        elevenlabs_voice_id=r.string("TTS", "elevenlabs_voice_id", ""),
        elevenlabs_model=r.string("TTS", "elevenlabs_model", ""),
        openai_voice=r.string("TTS", "openai_voice", ""),
        piper_multispeaker=r.boolean("TTS", "piper_multispeaker", False),
        piper_speakers=MappingProxyType(piper_speakers),
    )
    emotion = EmotionSettings(
        enabled=r.boolean("EMOTION", "enabled"),
        method=r.string("EMOTION", "emotion_method", "classifier"),
        model=r.string("EMOTION", "emotion_model", ""),
    )
    rag = RAGSettings(
        enabled=r.boolean("RAG", "enabled", True),
        enable_topic_tracking=r.boolean("RAG", "enable_topic_tracking", True),
        strategy=r.string("RAG", "strategy", "naive"),
        context_window=r.integer("RAG", "context_window", 2, 0),
        max_memories=r.integer("RAG", "max_memories", 3, 1),
        top_k=r.integer("RAG", "top_k", 5, 1),
        recency_boost_days=r.integer("RAG", "recency_boost_days", 7, 0),
        embedding_source=r.string("RAG", "embedding_source", "local"),
        embedding_url=r.string("RAG", "embedding_url", ""),
    )

    servo = ServoSettings(
        arms_present=r.boolean("SERVO", "arms_present"),
        movement_watchdog_enabled=r.boolean(
            "SERVO", "movement_watchdog_enabled", True
        ),
        movement_watchdog_timeout=r.number(
            "SERVO", "movement_watchdog_timeout", 45.0, 10.0, 120.0
        ),
        movement_stall_timeout=r.number(
            "SERVO", "movement_stall_timeout", 8.0, 6.0, 30.0
        ),
        left_up_height=r.integer("SERVO", "leftUpHeight"),
        left_down_height=r.integer("SERVO", "leftDownHeight"),
        perfect_left_height_offset=r.integer("SERVO", "perfectLeftHeightOffset"),
        right_up_height=r.integer("SERVO", "rightUpHeight"),
        right_down_height=r.integer("SERVO", "rightDownHeight"),
        perfect_right_height_offset=r.integer("SERVO", "perfectRightHeightOffset"),
        forward_left_leg=r.integer("SERVO", "forwardLeftLeg"),
        back_left_leg=r.integer("SERVO", "backLeftLeg"),
        perfect_left_leg_offset=r.integer("SERVO", "perfectLeftLegOffset"),
        forward_right_leg=r.integer("SERVO", "forwardRightLeg"),
        back_right_leg=r.integer("SERVO", "backRightLeg"),
        perfect_right_leg_offset=r.integer("SERVO", "perfectRightLegOffset"),
        left_main_min=r.integer("SERVO", "leftMainMin"),
        left_main_max=r.integer("SERVO", "leftMainMax"),
        left_main_offset=r.integer("SERVO", "leftMainOffset"),
        left_forearm_min=r.integer("SERVO", "leftForarmMin"),
        left_forearm_max=r.integer("SERVO", "leftForarmMax"),
        left_forearm_offset=r.integer("SERVO", "leftForearmOffset"),
        left_hand_min=r.integer("SERVO", "leftHandMin"),
        left_hand_max=r.integer("SERVO", "leftHandMax"),
        left_hand_offset=r.integer("SERVO", "leftHandOffset"),
        right_main_min=r.integer("SERVO", "rightMainMin"),
        right_main_max=r.integer("SERVO", "rightMainMax"),
        right_main_offset=r.integer("SERVO", "rightMainOffset"),
        right_forearm_min=r.integer("SERVO", "rightForarmMin"),
        right_forearm_max=r.integer("SERVO", "rightForarmMax"),
        right_forearm_offset=r.integer("SERVO", "rightForearmOffset"),
        right_hand_min=r.integer("SERVO", "rightHandMin"),
        right_hand_max=r.integer("SERVO", "rightHandMax"),
        right_hand_offset=r.integer("SERVO", "rightHandOffset"),
    )
    _validate_servo_targets(r, servo)

    access = AccessSettings(
        webui_enabled=r.boolean("ACCESS", "webui_enabled", True),
        webui_port=r.integer("ACCESS", "webui_port", 80, 1, 65535),
        webui_password=r.string("ACCESS", "webui_password", ""),
        webui_theme=r.string("ACCESS", "webui_theme", "default", allow_empty=False),
        remote_access_enabled=r.boolean("ACCESS", "remote_access_enabled", False),
    )
    ui = UISettings(
        enabled=r.boolean("UI", "UI_enabled"),
        camera_enabled=r.boolean("UI", "use_camera_module"),
        show_mouse=r.boolean("UI", "show_mouse"),
        fullscreen=r.boolean("UI", "fullscreen"),
        screen_width=r.integer("UI", "screen_width", 480, 1),
        screen_height=r.integer("UI", "screen_height", 320, 1),
        rotation=r.integer("UI", "rotation", 0, choices=(0, 90, 180, 270)),
        show_time=r.boolean("UI", "show_time", True),
        show_cpu_temp=r.boolean("UI", "show_cpu_temp", False),
        ampm_format=r.boolean("UI", "ampm_format", True),
        app=r.string("UI", "app", "terminal", allow_empty=False),
        target_fps=r.integer("UI", "target_fps", 30, 1, 240),
        font_size=r.integer("UI", "font_size", 12, 1, 100),
        screensaver_timer=r.integer("UI", "screensaver_timer", 300, 0),
        screensaver_cycle_interval=r.integer("UI", "screensaver_cycle_interval", 300, 1),
        screensaver_list=tuple(
            item.strip()
            for item in r.string("UI", "screensaver_list", "random").split(",")
            if item.strip()
        ) or ("random",),
    )
    battery = BatterySettings(
        enabled=r.boolean("BATTERY", "battery_enabled", False),
        auto_shutdown=r.boolean("BATTERY", "battery_auto_shutdown", False),
        capacity_mah=r.integer("BATTERY", "battery_capacity_mAh", 3000, 1),
        initial_voltage=r.number("BATTERY", "battery_initial_voltage", 12.0, 0.1),
        cutoff_voltage=r.number("BATTERY", "battery_cutoff_voltage", 10.0, 0.0),
    )
    if battery.cutoff_voltage >= battery.initial_voltage:
        r.errors.append("[BATTERY] battery_cutoff_voltage must be below battery_initial_voltage")

    if r.errors:
        # Avoid flooding startup output with duplicate missing-section reports.
        raise ConfigValidationError(tuple(dict.fromkeys(r.errors)))

    return TypedConfig(
        source=source,
        controls=controls,
        audio=audio,
        character=character,
        stt=stt,
        llm=llm,
        vision=vision,
        tts=tts,
        emotion=emotion,
        rag=rag,
        servo=servo,
        access=access,
        ui=ui,
        battery=battery,
        sections=_immutable_sections(parser),
    )


def load_typed_config(path) -> TypedConfig:
    path = Path(path).resolve()
    return parse_typed_config(_read_parser(path), path)


def validate_ini_file(path) -> None:
    """Validate INI syntax without requiring the full TARS schema."""
    _read_parser(Path(path).resolve())


def validate_typed_config_file(path) -> None:
    """Validate INI syntax, field types, ranges, and servo endpoints."""
    load_typed_config(path)


def _thread_lock_for(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


class _InterprocessLock:
    def __init__(self, path: Path, timeout: float):
        self.path = path
        self.timeout = max(0.1, float(timeout))
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"\0")
            self.handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    self.handle.close()
                    self.handle = None
                    raise TimeoutError(f"Timed out waiting for configuration lock: {self.path}")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


@contextmanager
def config_write_lock(path, timeout: float = 5.0) -> Iterator[None]:
    """Serialize configuration writers across threads and processes."""
    target = Path(path).resolve()
    thread_lock = _thread_lock_for(target)
    with thread_lock:
        with _InterprocessLock(target.with_name(target.name + ".lock"), timeout):
            yield


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _backup_existing(path: Path, backup_path: Optional[Path], keep_history: bool) -> None:
    if not path.exists():
        return
    stable = backup_path or path.with_name(f"{path.stem}_backup{path.suffix}")
    shutil.copy2(path, stable)
    if not keep_history:
        return
    history_dir = path.parent / "config_backups"
    history_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    historical = history_dir / f"{path.stem}-{stamp}{path.suffix}"
    shutil.copy2(path, historical)
    backups = sorted(history_dir.glob(f"{path.stem}-*{path.suffix}"))
    for old_backup in backups[:-10]:
        try:
            old_backup.unlink()
        except OSError:
            pass


def atomic_write_text(
    path,
    text: str,
    *,
    validator: Optional[Callable[[Path], None]] = validate_ini_file,
    backup_path=None,
    create_backup: bool = True,
    keep_history: bool = False,
    lock_timeout: float = 5.0,
) -> None:
    """Durably replace a text file after validating the completed temporary.

    The temporary is created in the target directory so ``os.replace`` is an
    atomic rename on the same filesystem.  Callers never expose a half-written
    configuration, even if writing or validation fails.
    """
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(backup_path).resolve() if backup_path is not None else None

    with config_write_lock(target, timeout=lock_timeout):
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            if validator is not None:
                validator(temporary)
            if target.exists():
                try:
                    os.chmod(temporary, target.stat().st_mode)
                except OSError:
                    pass
            if create_backup:
                _backup_existing(target, backup, keep_history)
            os.replace(temporary, target)
            _fsync_directory(target.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def atomic_update_text(
    path,
    transform: Callable[[str], str],
    **write_options,
) -> None:
    """Read, transform, and atomically replace a file under one lock."""
    target = Path(path).resolve()
    with config_write_lock(target, timeout=write_options.pop("lock_timeout", 5.0)):
        current = target.read_text(encoding="utf-8")
        updated = transform(current)
        # The outer lock is re-entrant in-process; the interprocess lock is not,
        # so perform the write inline instead of calling atomic_write_text.
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            validator = write_options.pop("validator", validate_ini_file)
            if validator is not None:
                validator(temporary)
            try:
                os.chmod(temporary, target.stat().st_mode)
            except OSError:
                pass
            if write_options.pop("create_backup", True):
                backup_path = write_options.pop("backup_path", None)
                backup = Path(backup_path).resolve() if backup_path is not None else None
                _backup_existing(
                    target,
                    backup,
                    bool(write_options.pop("keep_history", False)),
                )
            if write_options:
                raise TypeError(f"Unknown atomic write options: {', '.join(write_options)}")
            os.replace(temporary, target)
            _fsync_directory(target.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
