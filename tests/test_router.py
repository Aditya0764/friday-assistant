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


def _echo_reply(sentence):
    route = Router(build_registry()).route(sentence)
    assert route.skill is not None, f"{sentence!r} was not claimed by any skill"
    assert route.skill.name == "echo"
    return route.skill.run(route.args)


@pytest.mark.parametrize(
    ("sentence", "reply"),
    [
        ("Can you repeat after me, testing one two three", "testing one two three"),
        ("Please echo hello Friday", "hello friday"),
        ("Could you please echo good morning", "good morning"),
        ("Friday, repeat after me I am ready", "i am ready"),
        ("Hey Friday, can you echo hi", "hi"),
        ("Would you please repeat after me hello", "hello"),
    ],
)
def test_echo_accepts_a_lead_in(sentence, reply):
    assert _echo_reply(sentence) == reply


def test_echo_lead_in_with_nothing_to_repeat_says_so():
    assert _echo_reply("Please echo") == "You didn't say anything to repeat."
    assert _echo_reply("Can you repeat after me?") == "You didn't say anything to repeat."


@pytest.mark.parametrize(
    "sentence",
    [
        "Say after me I am ready",
        "I said please echo hello",
        "Would it echo in the hall",
        "Can you read my notes",
    ],
)
def test_echo_does_not_take_other_sentences(sentence):
    route = Router(build_registry()).route(sentence)
    assert route.skill is None or route.skill.name != "echo"


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