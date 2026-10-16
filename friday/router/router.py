"""Router: rules first, then (optionally) the trained model, then the LLM.

route(text) cleans the sentence and asks the skill registry who can handle it.
1. A skill that says yes is a rule match (via="rule"). Rules and the catch skill always win.
2. If nobody took it and a model classifier is given, the model guesses the intent:
   - doc_qa with confidence >= threshold runs the docs skill (via="model"). Docs answers from
     the document or says it can't, so a wrong guess is safe.
   - lists_notes / timers_reminders / music with confidence >= threshold: Route.slots_for is
     set, so the graph asks the LLM for the details (friday.router.slots). If that fails, the
     catch skill (already in Route.skill) answers "please say it again".
   - any other skill class at confidence >= threshold: "please say it again" (catch skill).
   - "other", or confidence below the threshold, goes to the LLM (via="llm"). The guess is still
     kept in Route.model / Route.conf so it can be logged.
3. No model (the default), or it isn't ready yet: the sentence goes to the LLM (skill=None).

can_handle receives the CLEAN text (lowercase, no punctuation, but numbers and
math symbols survive: "What's 18% of 2,400?" -> "what's 18% of 2400").
args["text"] is what the user said; args["clean"] is the cleaned version.

Run `python -m friday.router.router` for the self-test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from friday.router.model import DEFAULT_THRESHOLD
from friday.skills.base import Skill, SkillRegistry

# Router classes whose details (slots) the LLM can fill, and the skill that then runs.
SLOT_SKILLS = {"lists_notes": "lists", "timers_reminders": "reminders", "music": "music"}


class Classifier(Protocol):
    def classify(self, clean: str) -> tuple[str, float] | None: ...


@dataclass(frozen=True)
class Route:
    skill: Skill | None  # None = send to the LLM
    args: dict[str, str] = field(default_factory=dict)
    via: str = "llm"  # "rule", "model" or "llm"
    model: str = ""  # the model's guess, when it was asked (even if not used)
    conf: float = 0.0  # confidence of that guess
    slots_for: str = ""  # router class whose slots the graph should fill, else ""


def normalize(text: str) -> str:
    """Lowercase and drop punctuation, but keep what math and conversions need.

    Kept: apostrophes, % + - * / ^ ( ), and dots inside numbers (3.5).
    Thousands commas inside numbers are removed (2,400 -> 2400).
    Curly apostrophes (what phones type: What’s) become plain ones first.
    """
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    text = re.sub(r"[^\w\s'%+\-*/^().]", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class Router:
    def __init__(
        self,
        registry: SkillRegistry,
        classifier: Classifier | None = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self.registry = registry
        self.classifier = classifier
        self.threshold = threshold

    def route(self, text: str) -> Route:
        clean = normalize(text)
        args = {"text": text, "clean": clean}
        skill = self.registry.find(clean)
        if skill is not None:
            return Route(skill=skill, args=args, via="rule")
        guess = self.classifier.classify(clean) if self.classifier and clean else None
        if guess is None:
            return Route(skill=None, args=args, via="llm")
        label, conf = guess
        if label != "other" and conf >= self.threshold:
            slots_for = ""
            if label == "doc_qa":
                target = self.registry.get("docs")
            else:
                target = self.registry.get("catch")
                wanted = SLOT_SKILLS.get(label, "")
                if wanted and self.registry.get(wanted) is not None:
                    slots_for = label
            if target is not None:
                return Route(
                    skill=target, args=args, via="model", model=label, conf=conf,
                    slots_for=slots_for,
                )
        return Route(skill=None, args=args, via="llm", model=label, conf=conf)


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