"""Remove the wake phrase from what Whisper heard after the wake word (P6-04).

Preferred: cut by time (words_after_cut), so a misheard "Hey Freddy" goes too. Fallback: a regex
for a leading "hey friday" / "friday" (strip_wake_phrase)."""

from __future__ import annotations

import re

_LEAD = re.compile(
    r"^\s*(?:(?:hey|he|hi|hello|okay|ok)[\s,]+)?friday\b(?!['\u2019])[\s,.:;!?-]*",
    re.IGNORECASE,
)


def words_after_cut(
    words: tuple[tuple[str, float, float], ...] | None, cut_s: float
) -> str | None:
    """The wake path: keep the words that END at or after cut_s seconds (a word straddling the
    cut stays). None when there are no timestamps or nothing is left, so the caller falls back
    to strip_wake_phrase."""
    if not words:
        return None
    text = "".join(word for word, _start, end in words if end >= cut_s).strip()
    return text or None


def strip_wake_phrase(text: str) -> str:
    """"Hey Friday, what time is it?" -> "what time is it?". If nothing else was said, the
    original text is kept, so a bare "Friday" still gets a reply."""
    stripped = _LEAD.sub("", text, count=1).strip()
    return stripped or text.strip()