"""Clock skill: the current time and today's date or day.

"What time is it?", "What's the date?", "What day is it?" Both at once also works.
The WHOLE sentence has to be a plain time or date question (a lead-in such as "can you tell me"
and a tail such as "right now" are fine). Anything with more in it, like a place ("what time is it
in Tokyo"), another day ("what day is it tomorrow") or another topic ("what time is the meeting",
"what's the time complexity of quicksort"), is not claimed and goes to the LLM.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from friday.skills.base import Skill

# Questions that stand on their own.
_TIME_WH = r"(?:what time (?:is it|it is)|what(?:'s| is)? the (?:current )?time(?: is)?)"
_TIME_FIXED = r"(?:current time|time right now)"
_DATE_WH = (
    r"(?:what(?:'s| is) (?:the date|today's date|the day today|the date today|the day of the week)"
    r"|(?:what|which) (?:date|day) (?:is it|it is)|what day is today"
    r"|(?:what|which) day of the week (?:is it|it is)"
    r"|what(?:'s| is) the (?:time and date|date and time))"
)
_DATE_FIXED = r"today's date"
_SOLO = rf"(?:{_TIME_WH}|{_TIME_FIXED}|{_DATE_WH}|{_DATE_FIXED})"
_PLAIN = rf"{_SOLO}(?: and {_SOLO})*"
# Noun phrases that only count after a request ("tell me the time", "got the time").
_ASKED = r"(?:the (?:current )?time|the date|today's date|the (?:time and date|date and time))"

_ASK = (
    r"(?:(?:can|could|would) you (?:please )?(?:tell me |give me )?|please (?:tell me )?"
    r"|tell me |do you (?:happen to )?know |do you have |have you got |got )"
)
_HEY = r"(?:(?:hey )?friday )?"
_TAIL = r"(?: (?:right now|now|today|currently|at the moment|please))*"
_SENTENCE = re.compile(rf"{_HEY}(?:{_ASK}?{_PLAIN}|{_ASK}{_ASKED}){_TAIL}")

_TIME_WORD = re.compile(r"\btime\b")
_DATE_WORD = re.compile(r"\b(?:date|day)\b|today's")


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _wants(text: str) -> tuple[bool, bool] | None:
    """(wants the time, wants the date) if the whole sentence is a clock question, else None."""
    text = text.strip()
    if not _SENTENCE.fullmatch(text):
        return None
    return bool(_TIME_WORD.search(text)), bool(_DATE_WORD.search(text))


class ClockSkill(Skill):
    name = "clock"

    def __init__(self, now_fn: Callable[[], datetime] = _local_now) -> None:
        self._now = now_fn

    def can_handle(self, text: str) -> bool:
        return _wants(text) is not None

    def run(self, args: dict[str, str]) -> str:
        wants = _wants(args["clean"])
        want_time, want_date = wants if wants else (False, False)
        now = self._now()
        parts = []
        if want_time:
            parts.append(f"It is {now.strftime('%I:%M %p').lstrip('0')}.")
        if want_date:
            parts.append(f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}.")
        return " ".join(parts)
