"""Dummy skill: tells the current time. Real time/date/math skill comes in P4-01."""

from __future__ import annotations

from datetime import datetime

from friday.skills.base import Skill

PHRASES = ("what time is it", "what's the time", "what is the time", "tell me the time", "current time")


class ClockSkill(Skill):
    name = "clock"

    def can_handle(self, text: str) -> bool:
        return any(phrase in text for phrase in PHRASES)

    def run(self, args: dict[str, str]) -> str:
        now = datetime.now().astimezone()
        return f"It is {now.strftime('%I:%M %p').lstrip('0')}."