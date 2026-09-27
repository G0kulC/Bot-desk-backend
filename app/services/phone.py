from __future__ import annotations

import re

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_e164(raw: str, default_country: str = "91") -> str:
    """Normalise an Indian-style phone number to E.164 (+91XXXXXXXXXX).

    Accepts '+91 98400 12345', '098400 12345', '9840012345', '919840012345'.
    """
    s = re.sub(r"[\s\-().]", "", raw or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if not s.startswith("+"):
        digits = s.lstrip("0") if len(s) == 11 and s.startswith("0") else s
        if len(digits) == 10:
            s = f"+{default_country}{digits}"
        elif len(digits) == 12 and digits.startswith(default_country):
            s = f"+{digits}"
        else:
            s = f"+{digits}"
    if not _E164.match(s):
        raise ValueError(f"Not a valid phone number: {raw!r}")
    return s


def to_wa_id(phone: str | None) -> str:
    """WhatsApp ids are E.164 digits without '+'."""
    return re.sub(r"\D", "", phone or "")
