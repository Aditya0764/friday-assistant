import pytest

from friday.router.router import Router
from friday.skills.catch import REPLY, CatchSkill
from friday.skills.registry import build_registry


class _FakeScheduler:
    def add(self, text, due_at):
        return 1


def _route(sentence, tmp_path, scheduler=None):
    return Router(build_registry(scheduler, tmp_path / "t.db")).route(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "I'll milk to my shopping list.",
        "I take and bread to my shopping list.",
        "and exit break to my shopping list",
        "I take time to break through my shopping list.",
        "Edd eggs on the shopping list",
    ],
)
def test_garbled_list_commands_get_try_again(sentence, tmp_path):
    route = _route(sentence, tmp_path)
    assert route.skill is not None
    assert route.skill.name == "catch"
    assert route.skill.run(route.args) == REPLY


def test_garbled_reminder_gets_try_again(tmp_path):
    route = _route("Remind me to apply it to 6 jobs.", tmp_path, _FakeScheduler())
    assert route.skill.name == "catch"


def test_reminder_words_are_left_alone_without_a_scheduler(tmp_path):
    assert _route("Remind me to apply it to 6 jobs.", tmp_path).skill is None


@pytest.mark.parametrize(
    "sentence",
    [
        "Tell me a fun fact.",
        "What is the capital of France?",
        "I will do my shopping with an online app.",
        "What should I put in a good shopping list for a party?",
        "Play Blinding Lights.",
        "How do timers work?",
    ],
)
def test_normal_chat_still_goes_to_the_llm(sentence, tmp_path):
    assert _route(sentence, tmp_path, _FakeScheduler()).skill is None


def test_real_skills_win_over_the_catch_skill(tmp_path):
    for sentence, skill in (
        ("Add milk to my shopping list.", "lists"),
        ("What's on my shopping list?", "lists"),
        ("Remind me at 6 to apply for jobs.", "reminders"),
        ("Set a timer for 5 minutes.", "reminders"),
    ):
        assert _route(sentence, tmp_path, _FakeScheduler()).skill.name == skill


def test_catch_is_registered_last(tmp_path):
    assert build_registry(_FakeScheduler(), tmp_path / "t.db").names()[-1] == "catch"
    assert CatchSkill().name == "catch"