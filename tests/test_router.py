import pytest

from friday.router.router import Router, normalize
from friday.skills.base import Skill, SkillRegistry
from friday.skills.registry import build_registry


class _Dummy(Skill):
    name = "dummy"

    def can_handle(self, text):
        return text == "dummy"

    def run(self, args):
        return "ok"


def test_normalize_lowercases_and_strips_punctuation():
    assert normalize("  What's the TIME?!  ") == "what's the time"


def test_normalize_collapses_spaces():
    assert normalize("repeat   after,  me.") == "repeat after me"


def test_normalize_keeps_numbers_and_math_symbols():
    assert normalize("What's 18% of 2,400?") == "what's 18% of 2400"
    assert normalize("Calculate (2 + 3) * 4.") == "calculate (2 + 3) * 4"
    assert normalize("What is 3.5 times 2?") == "what is 3.5 times 2"


@pytest.mark.parametrize(
    ("sentence", "skill_name"),
    [
        ("What time is it?", "clock"),
        ("What's the time?", "clock"),
        ("Echo hello Friday.", "echo"),
        ("Repeat after me, I am building Friday.", "echo"),
    ],
)
def test_known_phrases_route_to_skill(sentence, skill_name):
    route = Router(build_registry()).route(sentence)
    assert route.via == "rule"
    assert route.skill is not None
    assert route.skill.name == skill_name


def test_unknown_sentence_goes_to_llm():
    route = Router(build_registry()).route("Tell me a fun fact.")
    assert route.skill is None
    assert route.via == "llm"


def test_empty_sentence_goes_to_llm():
    route = Router(build_registry()).route("")
    assert route.skill is None
    assert route.via == "llm"


def test_echo_with_nothing_to_repeat_says_so():
    route = Router(build_registry()).route("Echo.")
    assert route.skill is not None
    assert route.skill.run(route.args) == "You didn't say anything to repeat."


def test_registry_rejects_duplicate_names():
    registry = SkillRegistry()
    registry.register(_Dummy())
    with pytest.raises(ValueError):
        registry.register(_Dummy())


def test_registry_rejects_empty_name():
    class NoName(_Dummy):
        name = ""

    with pytest.raises(ValueError):
        SkillRegistry().register(NoName())