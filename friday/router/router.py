"""Router v0: rules first, LLM fallback.

route(text) cleans the sentence and asks the skill registry who can handle it.
A skill that says yes is a rule match (via="rule"). If none does, the sentence
goes to the LLM (skill=None, via="llm").

can_handle receives the CLEAN text (lowercase, no punctuation, but numbers and
math symbols survive: "What's 18% of 2,400?" -> "what's 18% of 2400").
args["text"] is what the user said; args["clean"] is the cleaned version.

The trained router (Phase 6) replaces this file. Callers keep using route().
Run `python -m friday.router.router` for the self-test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from friday.skills.base import Skill, SkillRegistry


@dataclass(frozen=True)
class Route:
    skill: Skill | None  # None = send to the LLM
    args: dict[str, str] = field(default_factory=dict)
    via: str = "llm"  # "rule" or "llm"


def normalize(text: str) -> str:
    """Lowercase and drop punctuation, but keep what math and conversions need.

    Kept: apostrophes, % + - * / ^ ( ), and dots inside numbers (3.5).
    Thousands commas inside numbers are removed (2,400 -> 2400).
    """
    text = text.lower()
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    text = re.sub(r"[^\w\s'%+\-*/^().]", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class Router:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def route(self, text: str) -> Route:
        clean = normalize(text)
        args = {"text": text, "clean": clean}
        skill = self.registry.find(clean)
        if skill is None:
            return Route(skill=None, args=args, via="llm")
        return Route(skill=skill, args=args, via="rule")


if __name__ == "__main__":
    # Self-test with two throwaway skills defined right here.
    class RepeatSkill(Skill):
        name = "repeat"

        def can_handle(self, text: str) -> bool:
            return text.startswith("repeat after me")

        def run(self, args: dict[str, str]) -> str:
            return args["clean"].removeprefix("repeat after me").strip()

    class TimeSkill(Skill):
        name = "time"

        def can_handle(self, text: str) -> bool:
            return "what time is it" in text or "what's the time" in text

        def run(self, args: dict[str, str]) -> str:
            return "It is time to build."

    registry = SkillRegistry()
    registry.register(RepeatSkill())
    registry.register(TimeSkill())
    router = Router(registry)

    for sentence in (
        "What's the time?",
        "Repeat after me, hello Friday.",
        "Tell me a fun fact.",
        "",
    ):
        result = router.route(sentence)
        if result.skill is None:
            print(f"{sentence!r} -> LLM (via {result.via})")
        else:
            print(f"{sentence!r} -> {result.skill.name} (via {result.via}): {result.skill.run(result.args)!r}")