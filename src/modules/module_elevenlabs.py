import io
import re
import asyncio
import os
import hashlib
import requests
from modules.module_config import load_config

from modules.module_messageQue import queue_message

CONFIG = load_config()


class ElevenLabsQuotaError(RuntimeError):
    """The configured ElevenLabs account cannot accept more TTS requests."""


_elevenlabs_unavailable_reason = None
_SPEECH_NORMALIZATION_VERSION = "contractions-v1"

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

if CONFIG['TTS']['ttsoption'] == 'elevenlabs':
    _voice_id = CONFIG['TTS']['elevenlabs_voice_id'] or ''
    _model_id = CONFIG['TTS']['elevenlabs_model'] or ''
    if CONFIG['TTS']['elevenlabs_api_key'] and _voice_id:
        queue_message(
            f"LOAD: ElevenLabs custom voice ready "
            f"(voice ...{_voice_id[-6:]}, model {_model_id})"
        )
    else:
        queue_message(
            "ERROR: ElevenLabs is selected but ELEVENLABS_API_KEY or "
            "elevenlabs_voice_id is missing"
        )


# Contractions whose expansion is unambiguous.  Ambiguous forms such as
# "I'd" ("I had" or "I would") and "he's" ("he is" or "he has") are left
# alone so pronunciation cleanup cannot change the meaning of a response.
_CONTRACTION_EXPANSIONS = {
    "aren't": "are not",
    "can't": "cannot",
    "couldn't": "could not",
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "hadn't": "had not",
    "hasn't": "has not",
    "haven't": "have not",
    "isn't": "is not",
    "let's": "let us",
    "mightn't": "might not",
    "mustn't": "must not",
    "needn't": "need not",
    "shan't": "shall not",
    "shouldn't": "should not",
    "wasn't": "was not",
    "weren't": "were not",
    "won't": "will not",
    "wouldn't": "would not",
}
_CONTRACTION_PATTERN = re.compile(
    r"\b(?:" + "|".join(
        sorted((re.escape(item) for item in _CONTRACTION_EXPANSIONS), key=len, reverse=True)
    ) + r")\b",
    re.IGNORECASE,
)
_APOSTROPHE_TRANSLATION = str.maketrans({
    "\u2018": "'",  # left single quotation mark
    "\u2019": "'",  # right single quotation mark
    "\u02bc": "'",  # modifier letter apostrophe
    "\uff07": "'",  # full-width apostrophe
})


def _match_case(replacement, original):
    """Apply the contraction's capitalization to its spoken expansion."""
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def normalize_contractions_for_speech(text):
    """Expand English contractions in ElevenLabs-bound text only.

    The UI and conversation history retain the original response.  Normalizing
    here prevents voices from reading contractions such as ``I'll`` as the
    unrelated word ``ill``.  Both straight and typographic apostrophes are
    accepted because LLM output may contain either form.
    """
    if not isinstance(text, str) or not text:
        return text

    normalized = text.translate(_APOSTROPHE_TRANSLATION)
    normalized = _CONTRACTION_PATTERN.sub(
        lambda match: _match_case(
            _CONTRACTION_EXPANSIONS[match.group(0).lower()],
            match.group(0),
        ),
        normalized,
    )

    # These suffixes have one consistent expansion.  Keeping them separate
    # also covers pronouns beyond a fixed word list (for example, "someone'll").
    suffixes = (
        (re.compile(r"\b([A-Za-z]+)'ll\b", re.IGNORECASE), "will"),
        (re.compile(r"\b([A-Za-z]+)'re\b", re.IGNORECASE), "are"),
        (re.compile(r"\b([A-Za-z]+)'ve\b", re.IGNORECASE), "have"),
        (re.compile(r"\b([A-Za-z]+)'m\b", re.IGNORECASE), "am"),
    )
    for pattern, expansion in suffixes:
        normalized = pattern.sub(
            lambda match, word=expansion: f"{match.group(1)} {word}",
            normalized,
        )
    return normalized


def split_into_sentences(text, max_length=80):
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if current_chunk and len(current_chunk + " " + sentence) > max_length:
            chunks.append(current_chunk)
            current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [text]

def get_cache_filename(text):
    # A wake response generated with one voice/model must never be reused
    # after the user selects a different custom voice.
    identity = "|".join((
        str(CONFIG['TTS']['elevenlabs_voice_id'] or ''),
        str(CONFIG['TTS']['elevenlabs_model'] or ''),
        _SPEECH_NORMALIZATION_VERSION,
        text,
    ))
    text_hash = hashlib.md5(identity.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f"elevenlabs_{text_hash}.mp3")


def _request_speech(text, streaming=False):
    """Call ElevenLabs using its documented REST contract.

    This intentionally uses ``requests`` rather than the optional ElevenLabs
    SDK, so selecting ElevenLabs cannot silently become unavailable merely
    because that otherwise-unused package is absent from the Pi environment.
    """
    global _elevenlabs_unavailable_reason

    if _elevenlabs_unavailable_reason:
        raise ElevenLabsQuotaError(_elevenlabs_unavailable_reason)

    api_key = CONFIG['TTS']['elevenlabs_api_key']
    voice_id = CONFIG['TTS']['elevenlabs_voice_id']
    model_id = CONFIG['TTS']['elevenlabs_model']

    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured in .env")
    if not voice_id:
        raise RuntimeError("elevenlabs_voice_id is not configured in config.ini")

    suffix = "/stream" if streaming else ""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}{suffix}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    # output_format is a query parameter in the current ElevenLabs API.  The
    # previous implementation sent it, optimize_streaming_latency, and an
    # unsupported enable_ssml field in the JSON body, which can return 422.
    params = {"output_format": "mp3_44100_128"}
    payload = {"text": text, "model_id": model_id}
    response = requests.post(
        url,
        headers=headers,
        params=params,
        json=payload,
        timeout=(10, 60),
    )
    if response.status_code != 200:
        detail = response.text[:500].replace("\n", " ")
        try:
            error_code = response.json().get("detail", {}).get("code", "")
        except Exception:
            error_code = ""
        if error_code == "quota_exceeded":
            _elevenlabs_unavailable_reason = (
                "ElevenLabs quota is exhausted; custom voice is disabled until "
                "credits are available and TARS is restarted"
            )
            raise ElevenLabsQuotaError(_elevenlabs_unavailable_reason)
        raise RuntimeError(f"ElevenLabs API returned {response.status_code}: {detail}")
    if not response.content:
        raise RuntimeError("ElevenLabs returned an empty audio response")
    return io.BytesIO(response.content)

async def synthesize_elevenlabs_streaming(chunk):
    """
    Synthesize using direct REST API to ensure SSML tags are processed.
    The Python SDK sometimes doesn't handle SSML properly, so we use direct HTTP.
    """
    try:
        # Check if model supports SSML
        model_id = CONFIG['TTS']['elevenlabs_model']
        is_eleven_v3 = 'v3' in model_id.lower()
        
        if is_eleven_v3 and '<break' in chunk:
            # Eleven V3 doesn't support SSML, log warning
            queue_message(f"WARNING: Model {model_id} doesn't support SSML tags. Use [pause], [short pause], [long pause] instead.")
        
        # Log the actual text being sent (for debugging)
        if '<break' in chunk:
            queue_message(f"DEBUG: Sending text with SSML: {chunk[:100]}...")

        audio_buffer = await asyncio.to_thread(_request_speech, chunk, True)
        audio_buffer.seek(0)
        return audio_buffer

    except ElevenLabsQuotaError as e:
        queue_message(f"ERROR: {e}")
        return None
    except Exception as e:
        queue_message(f"ERROR: ElevenLabs streaming failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def synthesize_elevenlabs_complete(text):
    """
    Synthesize complete speech using direct REST API.
    """
    try:
        # Check if model supports SSML
        model_id = CONFIG['TTS']['elevenlabs_model']
        is_eleven_v3 = 'v3' in model_id.lower()
        
        if is_eleven_v3 and '<break' in text:
            queue_message(f"WARNING: Model {model_id} doesn't support SSML tags. Use [pause], [short pause], [long pause] instead.")
        
        # Log if SSML is present
        if '<break' in text:
            queue_message(f"DEBUG: Sending wakeword with SSML: {text}")

        audio_buffer = await asyncio.to_thread(_request_speech, text, False)
        audio_buffer.seek(0)
        return audio_buffer

    except ElevenLabsQuotaError as e:
        queue_message(f"ERROR: {e}")
        return None
    except Exception as e:
        queue_message(f"ERROR: ElevenLabs synthesis failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def text_to_speech_with_pipelining_elevenlabs(text, is_wakeword):    

    # Normalize once, before sentence splitting and before looking up cached
    # wake responses.  Doing this at the pipeline boundary guarantees every
    # ElevenLabs path receives the spoken form, including cached responses.
    speech_text = normalize_contractions_for_speech(text)
    if speech_text != text:
        queue_message(
            f"TTS: ElevenLabs expanded contractions: {speech_text!r}"
        )

    if is_wakeword:
        cache_file = get_cache_filename(speech_text)

        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    audio_bytes = f.read()
                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                yield audio_buffer
                return
            except Exception as e:
                queue_message(f"ERROR: Failed to load cache: {e}")

        queue_message(f"Caching wakeword: {speech_text}")
        audio_buffer = await synthesize_elevenlabs_complete(speech_text)
        if audio_buffer:
            try:
                audio_bytes = audio_buffer.read()
                with open(cache_file, 'wb') as f:
                    f.write(audio_bytes)

                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                yield audio_buffer
            except Exception as e:
                queue_message(f"ERROR: Failed to cache: {e}")
                audio_buffer.seek(0)
                yield audio_buffer

    else:

        chunks = split_into_sentences(speech_text, max_length=80)
        for i, chunk in enumerate(chunks):
            audio_buffer = await synthesize_elevenlabs_streaming(chunk)
            if audio_buffer:
                yield audio_buffer
            else:
                queue_message(f"WARNING: Chunk {i+1} failed, skipping")
