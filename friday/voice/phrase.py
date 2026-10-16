"""Drop a leading "hey friday" / "friday" from what Whisper heard after the wake word (P6-04)."""

from __future__ import annotations

import re

_LEAD = re.compile(
    r"^\s*(?:(?:hey|he|hi|hello|okay|ok)[\s,]+)?friday\b(?!['\u2019])[\s,.:;!?-]*",
    re.IGNORECASE,
)


def strip_wake_phrase(text: str) -> str:
    """"Hey Friday, what time is it?" -> "what time is it?". If nothing else was said, the
    original text is kept, so a bare "Friday" still gets a reply."""
    stripped = _LEAD.sub("", text, count=1).strip()
    return stripped or text.strip()