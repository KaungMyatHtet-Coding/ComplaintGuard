"""Deterministic input normalization and script-based language detection."""

import re
import unicodedata
from typing import Literal

DetectedLanguage = Literal["en", "my", "mixed", "unsupported"]

_LATIN_LETTER = re.compile(r"[A-Za-z]")
_MYANMAR_LETTER = re.compile(r"[\u1000-\u109f\ua9e0-\ua9ff\uaa60-\uaa7f]")


def normalize_input(text: str) -> str:
    """Apply conservative NFC and whitespace normalization."""

    return " ".join(unicodedata.normalize("NFC", text).split())


def detect_language(text: str) -> DetectedLanguage:
    """Classify English, Myanmar, mixed, or unsupported input by script."""

    has_latin = bool(_LATIN_LETTER.search(text))
    has_myanmar = bool(_MYANMAR_LETTER.search(text))
    if has_latin and has_myanmar:
        return "mixed"
    if has_myanmar:
        return "my"
    if has_latin:
        return "en"
    return "unsupported"
