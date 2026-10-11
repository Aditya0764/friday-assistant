"""Dummy skill: repeats what you tell it. "Echo hello" or "Repeat after me hello"."""

from __future__ import annotations

from friday.skills.base import Skill

PREFIXES = ("repeat after me", "echo")


class EchoSkill(Skill):
    name = "echo"

    def can_handle(self, text: str) -> bool:
        return text.startswith(PREFIXES)

    def run(self, args: dict[str, str]) -> str:
        clean = args["clean"]
        for prefix in PREFIXES:
            if clean.startswith(prefix):
                clean = clean.removeprefix(prefix).strip()
                break
        return clean or "You didn't say anything to repeat."