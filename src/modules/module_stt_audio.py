"""Pure audio preparation and noise-floor calculations for STT."""

from __future__ import annotations

import wave
from io import BytesIO

import numpy as np


NOISE_ARTIFACTS = frozenset({
    "uh", "um", "hm", "hmm", "mm", "mhm", "ah", "oh", "eh",
    "huh", "ha", "sh", "shh", "ss", "tt", "ts",
})


class STTAudioProcessor:
    def __init__(self, amp_gain: float):
        self.amp_gain = float(amp_gain)

    @staticmethod
    def compute_rms(data) -> float | None:  # noqa: ANN001
        if data.size == 0:
            return None
        flat = data.reshape(-1).astype(np.float64)
        if np.all(flat == 0):
            return None
        return float(np.sqrt(np.mean(np.square(flat))))

    def compute_amplified_rms(self, data) -> float | None:  # noqa: ANN001
        if data.size == 0:
            return None
        flat = data.reshape(-1).astype(np.float64) * self.amp_gain
        if np.all(flat == 0):
            return None
        return float(np.sqrt(np.mean(np.square(flat))))

    def amplify(self, data: np.ndarray) -> np.ndarray:
        return np.clip(data * self.amp_gain, -32768, 32767).astype(np.int16)

    @staticmethod
    def chunks_to_wav_buffer(chunks, sample_rate: int) -> BytesIO:  # noqa: ANN001
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            for chunk in chunks:
                wav.writeframes(chunk.tobytes())
        buffer.seek(0)
        return buffer

    @staticmethod
    def chunks_to_float32(chunks) -> np.ndarray:  # noqa: ANN001
        return np.concatenate(chunks).astype(np.float32).flatten() / 32768.0

    @staticmethod
    def meaningful_text(text: str) -> bool:
        if not text:
            return False
        cleaned = "".join(character for character in text if character.isalnum() or character == "_")
        return len(cleaned) >= 2 and cleaned.lower() not in NOISE_ARTIFACTS

    @staticmethod
    def noise_floor(rms_values) -> float | None:  # noqa: ANN001
        if not rms_values:
            return None
        values = np.asarray(rms_values, dtype=np.float64)
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        filtered = values[(values >= q1 - 1.5 * iqr) & (values <= q3 + 1.5 * iqr)]
        return float(np.max(filtered) if filtered.size else np.median(values))
