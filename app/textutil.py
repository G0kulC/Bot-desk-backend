from __future__ import annotations

import unicodedata


def strip_punctuation(text: str, keep: str = "") -> str:
    """Lowercase, replace punctuation/symbols with spaces and collapse whitespace.

    Unicode-aware: keeps letters, combining marks (Tamil/Devanagari vowel signs) and digits, which a
    plain `[^\\w\\s]` regex would strip.
    """
    out = [ch if (unicodedata.category(ch)[0] in "LMN" or ch in keep) else " " for ch in (text or "").lower()]
    return " ".join("".join(out).split())
