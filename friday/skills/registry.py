"""Builds the registry with every skill Friday has. Add new skills here.

Order matters: the first skill that can_handle a sentence wins.
Run `python -m friday.skills.registry` to check what the router does with a few sentences.
"""

from __future__ import annotations

from friday.skills.base import SkillRegistry
from friday.skills.calc import CalcSkill
from friday.skills.clock import ClockSkill
from friday.skills.echo import EchoSkill


def build_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(ClockSkill())
    registry.register(CalcSkill())
    return registry


if __name__ == "__main__":
    from friday.router.router import Router

    router = Router(build_registry())
    for sentence in (
        "What time is it?",
        "What's the date today?",
        "What's 18% of 2,400?",
        "Convert 5 km to miles.",
        "Echo hello Friday.",
        "Tell me a fun fact.",
    ):
        route = router.route(sentence)
        if route.skill is None:
            print(f"{sentence!r} -> LLM")
        else:
            print(f"{sentence!r} -> {route.skill.name}: {route.skill.run(route.args)!r}")