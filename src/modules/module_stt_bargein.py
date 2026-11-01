"""Text filtering policy for detecting user barge-in over TTS playback."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


NON_ALNUM_SPACE_RE = re.compile(r"[^a-zA-Z0-9\s]")
NOISE_WORDS = frozenset({
    "", "a", "i", "uh", "um", "ah", "oh", "hm", "hmm", "mm",
    "the", "is", "it", "to", "and", "of", "in", "that", "thats",
    "an", "or", "so", "do", "no", "my", "me", "we", "he", "she",
    "be", "at", "by", "if", "up", "as", "on", "you", "not", "but",
    "can", "got", "has", "had", "was", "are", "for", "too", "its",
    "all", "his", "her", "him", "our", "who", "how", "did", "get",
    "let", "may", "new", "now", "old", "one", "out", "own", "say",
    "set", "try", "two", "way", "yet", "any", "few", "per", "put",
})


def normalize_words(text: str) -> list[str]:
    return NON_ALNUM_SPACE_RE.sub("", str(text).lower()).split()


def find_novel_words(
    transcript: str,
    tts_words_all: set[str],
    window_words: set[str] | None = None,
    *,
    broad_threshold: float = 0.78,
    minimum_novel: int = 1,
) -> list[str]:
    heard_words = normalize_words(transcript)
    window_words = window_words or set()
    novel = []
    for word in heard_words:
        if word in NOISE_WORDS or len(word) <= 2:
            continue
        if word in tts_words_all or word in window_words:
            continue
        matched = False
        if len(word) >= 4:
            for tts_word in window_words | tts_words_all:
                if len(tts_word) >= 4 and abs(len(word) - len(tts_word)) <= 2:
                    if SequenceMatcher(None, word, tts_word).ratio() >= broad_threshold:
                        matched = True
                        break
        if not matched:
            novel.append(word)
    return novel if len(novel) >= int(minimum_novel) else []
