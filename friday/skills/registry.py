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
from friday.skills.lists import ListsSkill
from friday.skills.remind import ReminderSkill


def build_registry(scheduler=None, db_path=None) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(ClockSkill())
    registry.register(ListsSkill(db_path))  # before calc: 'add 5 to my list' is a list, not math
    registry.register(CalcSkill())
    if scheduler is not None:
        registry.register(ReminderSkill(scheduler))
    return registry


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from friday.router.router import Router

    class _PrintScheduler:
        """Stand-in for the real scheduler: just shows what would be saved."""

        def add(self, text, due_at):
            print(f"      (would save: {text!r} at {due_at:%Y-%m-%d %H:%M})")

    with tempfile.TemporaryDirectory() as folder:  # lists go to a throwaway database
        router = Router(build_registry(_PrintScheduler(), Path(folder) / "selftest.db"))
        for sentence in (
            "What time is it?",
            "What's 18% of 2,400?",
            "Remind me at 6 to apply for jobs.",
            "Set a timer for 5 minutes.",
            "Add milk to my shopping list.",
            "Add eggs and bread to my shopping list.",
            "What's on my shopping list?",
            "Remove eggs from my shopping list.",
            "Take a note that the demo is on Friday.",
            "Echo hello Friday.",
            "Tell me a fun fact.",
        ):
            route = router.route(sentence)
            if route.skill is None:
                print(f"{sentence!r} -> LLM")
            else:
                print(f"{sentence!r} -> {route.skill.name}: {route.skill.run(route.args)!r}")