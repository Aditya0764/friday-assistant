"""Dummy skill: repeats what you tell it. "Echo hello" or "Repeat after me hello".

A lead-in is fine before the trigger: "Can you repeat after me ...", "Please echo ...".
"""

from __future__ import annotations

import re

from friday.skills.base import Skill

PREFIXES = ("repeat after me", "echo")

_OPENING = r"(?:(?:hey )?friday )?(?:(?:can|could|would) you )?(?:please )?"
_TRIGGER = re.compile(rf"{_OPENING}(?:{'|'.join(PREFIXES)})")


class EchoSkill(Skill):
    name = "echo"

    def can_handle(self, text: str) -> bool:
        return _TRIGGER.match(text) is not None

    def run(self, args: dict[str, str]) -> str:
        clean = args["clean"]
        trigger = _TRIGGER.match(clean)
        if trigger:
            clean = clean[trigger.end() :].strip()
        return clean or "You didn't say anything to repeat."
