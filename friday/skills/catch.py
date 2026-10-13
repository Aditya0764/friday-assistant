"""Catch-all for garbled commands, so the LLM never pretends it did something.

Whisper sometimes mishears the first word ("add" -> "I'll"), so "Add milk to my shopping
list" arrives as "I'll milk to my shopping list". The real skills do not match it, the
sentence would go to the LLM, and the LLM happily says "Added!" while nothing was saved.

This skill is registered LAST. It only sees sentences that no real skill took, and if
they still clearly aim at a list, a reminder, a timer or the music, Friday asks you to
say it again.

Music: a SHORT sentence (6 words or fewer) with volume, music, song or spotify in it that
the music skill did not take is treated as a garbled music command.

Known cost: a chat question that ends like a list command ("Can you help me organise
my shopping list?") or a short remark about music ("I love this song") also gets
"please say it again". That is better than a false "Done".
"""

from __future__ import annotations

import re

from friday.skills.base import Skill

REPLY = "Sorry, I didn't catch that. Please say it again."

_LIST = re.compile(
    r"\b(?:my|our) (?:[a-z'-]+ )?list(?: please)?$"
    r"|\b(?:to|on|onto|into|from|off) (?:the|a) (?:[a-z'-]+ )?list(?: please)?$"
)
_REMINDER = re.compile(r"\bremind me\b|\b(?:set|start) (?:a |an )?(?:\d+ \w+ )?(?:timer|alarm)\b")
_MUSIC = re.compile(r"\b(?:volume|music|song|spotify)\b")
_MUSIC_MAX_WORDS = 6


class CatchSkill(Skill):
    name = "catch"

    def __init__(self, reminders: bool = True, music: bool = False) -> None:
        self._reminders = reminders  # False when the reminder scheduler is not running
        self._music = music  # True when the music skill is switched on

    def can_handle(self, text: str) -> bool:
        if _LIST.search(text):
            return True
        if self._reminders and _REMINDER.search(text):
            return True
        return (
            self._music
            and len(text.split()) <= _MUSIC_MAX_WORDS
            and _MUSIC.search(text) is not None
        )

    def run(self, args: dict[str, str]) -> str:
        return REPLY