"""Clock skill: the current time and today's date or day.

"What time is it?", "What's the date?", "What day is it?" Both at once also works.
Date arithmetic ("what day is it in 3 days") is not supported yet; it goes to the LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from friday.skills.base import Skill

TIME_PHRASES = (
    "what time is it",
    "what's the time",
    "what is the time",
    "tell me the time",
    "current time",
    "time right now",
)
DATE_PHRASES = (
    "what's the date",
    "what is the date",
    "what's today's date",
    "what is today's date",
    "today's date",
    "what date is it",
    "what day is it",
    "what's the day today",
    "what day is today",
    "which day is it",
)


def _local_now() -> datetime:
    return datetime.now().astimezone()


class ClockSkill(Skill):
    name = "clock"

    def __init__(self, now_fn: Callable[[], datetime] = _local_now) -> None:
        self._now = now_fn

    def can_handle(self, text: str) -> bool:
        return self._wants_time(text) or self._wants_date(text)

    def run(self, args: dict[str, str]) -> str:
        clean = args["clean"]
        now = self._now()
        parts = []
        if self._wants_time(clean):
            parts.append(f"It is {now.strftime('%I:%M %p').lstrip('0')}.")
        if self._wants_date(clean):
            parts.append(f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}.")
        return " ".join(parts)

    @staticmethod
    def _wants_time(text: str) -> bool:
        return any(phrase in text for phrase in TIME_PHRASES)

    @staticmethod
    def _wants_date(text: str) -> bool:
        return any(phrase in text for phrase in DATE_PHRASES)