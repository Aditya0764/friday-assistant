"""Skill interface and registry.

A skill is a plug-in with a name, a can_handle check, a run function and a
needs_approval flag. Adding a skill means writing one new class and registering
it. Nothing in the core changes.

args convention: args["text"] is always the raw sentence the user said. Later the
router adds extra keys (slots such as "song" or "time"), and skills use what they need.

Run `python -m friday.skills.base` for the plug-in self-test.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Skill(ABC):
    """Base class every skill inherits from."""

    name: str = ""
    needs_approval: bool = False  # True = the safety check must ask before run()

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        """Return True if this skill should handle the sentence."""

    @abstractmethod
    def run(self, args: dict[str, str]) -> str:
        """Do the job and return the reply text (spoken or shown to the user)."""


class SkillRegistry:
    """Holds the skills. The first registered skill that can_handle a sentence wins."""

    def __init__(self) -> None:
        self._skills: list[Skill] = []

    def register(self, skill: Skill) -> None:
        if not skill.name:
            raise ValueError("A skill needs a non-empty name.")
        if self.get(skill.name) is not None:
            raise ValueError(f"A skill named {skill.name!r} is already registered.")
        self._skills.append(skill)

    def get(self, name: str) -> Skill | None:
        for skill in self._skills:
            if skill.name == name:
                return skill
        return None

    def find(self, text: str) -> Skill | None:
        """Return the first skill that can handle the text, or None."""
        for skill in self._skills:
            if skill.can_handle(text):
                return skill
        return None

    def names(self) -> list[str]:
        return [skill.name for skill in self._skills]


if __name__ == "__main__":
    # Self-test: a dummy skill defined right here plugs in without touching the core.
    class ShoutSkill(Skill):
        name = "shout"

        def can_handle(self, text: str) -> bool:
            return text.lower().startswith("shout ")

        def run(self, args: dict[str, str]) -> str:
            return args["text"][6:].upper()

    registry = SkillRegistry()
    registry.register(ShoutSkill())
    print("Registered:", registry.names())

    for sentence in ("shout hello friday", "what time is it"):
        skill = registry.find(sentence)
        if skill is None:
            print(f"{sentence!r} -> no skill (this would go to the LLM)")
        else:
            reply = skill.run({"text": sentence})
            print(f"{sentence!r} -> {skill.name}: {reply!r} (needs_approval={skill.needs_approval})")

    try:
        registry.register(ShoutSkill())
    except ValueError as exc:
        print("Duplicate blocked:", exc)