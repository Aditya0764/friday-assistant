"""Catch-all for garbled commands, so the LLM never pretends it did something.

Whisper sometimes mishears the first word ("add" -> "I'll"), so "Add milk to my shopping
list" arrives as "I'll milk to my shopping list". The real skills do not match it, the
sentence would go to the LLM, and the LLM happily says "Added!" while nothing was saved.

This skill is registered LAST. It only sees sentences that no real skill took, and if
they still clearly aim at a list, a reminder or a timer, Friday asks you to say it again.

Known cost: a chat question that ends like a list command ("Can you help me organise
my shopping list?") also gets "please say it again". That is better than a false "Done".
Music ("play ...") is not caught here; the Spotify skill (P4-06) will own it.
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


class CatchSkill(Skill):
    name = "catch"

    def __init__(self, reminders: bool = True) -> None:
        self._reminders = reminders  # False when the reminder scheduler is not running

    def can_handle(self, text: str) -> bool:
        if _LIST.search(text):
            return True
        return self._reminders and _REMINDER.search(text) is not None

    def run(self, args: dict[str, str]) -> str:
        return REPLY