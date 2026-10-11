"""Builds the registry with every skill Friday has. Add new skills here.

Order matters: the first skill that can_handle a sentence wins.
Skills that need a running service (the reminder scheduler) are only added when
that service is passed in, so tests and self-checks can build a registry without it.
Run `python -m friday.skills.registry` to check what the router does with a few sentences.
"""

from __future__ import annotations

from friday.skills.base import SkillRegistry
from friday.skills.calc import CalcSkill
from friday.skills.clock import ClockSkill
from friday.skills.echo import EchoSkill
from friday.skills.remind import ReminderSkill


def build_registry(scheduler=None) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(ClockSkill())
    registry.register(CalcSkill())
    if scheduler is not None:
        registry.register(ReminderSkill(scheduler))
    return registry


if __name__ == "__main__":
    from friday.router.router import Router

    class _PrintScheduler:
        """Stand-in for the real scheduler: just shows what would be saved."""

        def add(self, text, due_at):
            print(f"      (would save: {text!r} at {due_at:%Y-%m-%d %H:%M})")

    router = Router(build_registry(_PrintScheduler()))
    for sentence in (
        "What time is it?",
        "What's 18% of 2,400?",
        "Remind me at 6 to apply for jobs.",
        "Remind me to stretch in 10 minutes.",
        "Set a timer for 5 minutes.",
        "Echo hello Friday.",
        "Tell me a fun fact.",
    ):
        route = router.route(sentence)
        if route.skill is None:
            print(f"{sentence!r} -> LLM")
        else:
            print(f"{sentence!r} -> {route.skill.name}: {route.skill.run(route.args)!r}")