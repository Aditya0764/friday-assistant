"""Builds the registry with every skill Friday has. Add new skills here.

Order matters: the first skill that can_handle a sentence wins.
Skills that need a running service (the reminder scheduler, the Spotify player) are only
added when that service is passed in, so tests and self-checks can build a registry without it.
The catch skill must stay last: it only handles garbled commands nobody else took.
Run `python -m friday.skills.registry` to check what the router does with a few sentences.
"""

from __future__ import annotations

from friday.skills.base import SkillRegistry
from friday.skills.calc import CalcSkill
from friday.skills.catch import CatchSkill
from friday.skills.clock import ClockSkill
from friday.skills.echo import EchoSkill
from friday.skills.lists import ListsSkill
from friday.skills.music import MusicSkill
from friday.skills.remind import ReminderSkill


def build_registry(scheduler=None, db_path=None, player=None) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(ClockSkill())
    registry.register(ListsSkill(db_path))  # before calc: 'add 5 to my list' is a list, not math
    registry.register(CalcSkill())
    if scheduler is not None:
        registry.register(ReminderSkill(scheduler))
    if player is not None:
        registry.register(MusicSkill(player))
    registry.register(CatchSkill(reminders=scheduler is not None, music=player is not None))  # always last
    return registry


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from friday.router.router import Router

    class _PrintScheduler:
        """Stand-in for the real scheduler: just shows what would be saved."""

        def add(self, text, due_at):
            print(f"      (would save: {text!r} at {due_at:%Y-%m-%d %H:%M})")

    class _PrintPlayer:
        """Stand-in for Spotify: just shows what would be asked of it."""

        def play(self, rest, title="", artist=""):
            print(f"      (would play: {rest!r})")
            return "Starboy by The Weeknd"

        def pause(self):
            print("      (would pause)")

    with tempfile.TemporaryDirectory() as folder:  # lists go to a throwaway database
        router = Router(build_registry(_PrintScheduler(), Path(folder) / "selftest.db", _PrintPlayer()))
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
            "I'll milk to my shopping list.",
            "Remind me to apply it to 6 jobs.",
            "Play Starboy by The Weeknd.",
            "Pause the music.",
            "Echo hello Friday.",
            "Tell me a fun fact.",
        ):
            route = router.route(sentence)
            if route.skill is None:
                print(f"{sentence!r} -> LLM")
            else:
                print(f"{sentence!r} -> {route.skill.name}: {route.skill.run(route.args)!r}")