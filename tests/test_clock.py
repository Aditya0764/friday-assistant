from datetime import datetime

import pytest

from friday.router.router import Router, normalize
from friday.skills.clock import ClockSkill
from friday.skills.registry import build_registry

_SUNDAY_5_05_PM = datetime(2026, 10, 11, 17, 5)  # a Sunday


def _run(sentence):
    skill = ClockSkill(now_fn=lambda: _SUNDAY_5_05_PM)
    clean = normalize(sentence)
    assert skill.can_handle(clean)
    return skill.run({"text": sentence, "clean": clean})


def test_time():
    assert _run("What time is it?") == "It is 5:05 PM."


def test_morning_time_has_no_leading_zero():
    skill = ClockSkill(now_fn=lambda: datetime(2026, 10, 11, 9, 7))
    assert skill.run({"text": "", "clean": "what time is it"}) == "It is 9:07 AM."


def test_date():
    assert _run("What's the date today?") == "Today is Sunday, 11 October 2026."


def test_day_question_gets_the_date_answer():
    assert _run("What day is it?") == "Today is Sunday, 11 October 2026."


def test_time_and_date_together():
    reply = _run("What's the time and what's the date?")
    assert reply == "It is 5:05 PM. Today is Sunday, 11 October 2026."


def test_other_questions_are_not_claimed():
    skill = ClockSkill()
    assert not skill.can_handle(normalize("What's today's weather?"))
    assert not skill.can_handle(normalize("Tell me a fun fact."))


_TIME = "It is 5:05 PM."
_DATE = "Today is Sunday, 11 October 2026."


@pytest.mark.parametrize(
    "sentence",
    [
        "Got the time?",
        "Have you got the time",
        "Do you have the time?",
        "Do you know what time it is?",
        "Do you know what the time is right now",
        "Can you tell me the time?",
        "Could you please tell me what time it is",
        "Please tell me the time",
        "Tell me what time it is",
        "Hey Friday, what time is it?",
        "What's the current time?",
        "What time is it right now?",
        "What time is it today?",
        "current time",
        "time right now",
    ],
)
def test_time_phrasings(sentence):
    assert _run(sentence) == _TIME


@pytest.mark.parametrize(
    "sentence",
    [
        "Which day of the week is it today",
        "What day of the week is it?",
        "Which day is it?",
        "What's the day today?",
        "What is today's date?",
        "Today's date",
        "What date is it?",
        "Tell me what day it is",
        "Tell me the date",
        "Can you tell me the date please",
    ],
)
def test_date_phrasings(sentence):
    assert _run(sentence) == _DATE


@pytest.mark.parametrize(
    "sentence",
    [
        "What's the time and date?",
        "What's the date and time?",
        "Tell me the time and date",
        "What's the time and what's the date?",
    ],
)
def test_time_and_date_phrasings_answer_both(sentence):
    assert _run(sentence) == f"{_TIME} {_DATE}"


@pytest.mark.parametrize(
    "sentence",
    [
        "What time is it in Tokyo?",
        "What time is it in the UK",
        "What's the time in London right now",
        "What time is it in IST",
        "What day is it tomorrow?",
        "What day is it in 3 days?",
        "What time is it in 3 hours?",
        "What time is the meeting?",
        "What time does the library open?",
        "What is the time complexity of quicksort?",
        "What's the date of Independence Day?",
        "What day is Diwali?",
        "I don't know what time it is",
        "Add what time is it to my list",
        "Play what time is it",
        "the time",
        "time",
    ],
)
def test_places_other_days_and_other_topics_are_not_the_clock(sentence):
    assert not ClockSkill().can_handle(normalize(sentence))


def _router(tmp_path):
    return Router(build_registry(None, tmp_path / "t.db", object()))


@pytest.mark.parametrize(
    "sentence",
    ["What time is it in Tokyo?", "What day is it tomorrow?", "What is the time complexity of quicksort?"],
)
def test_router_hands_place_and_other_day_questions_to_the_llm(sentence, tmp_path):
    assert _router(tmp_path).route(sentence).skill is None


def test_clock_no_longer_steals_from_lists_or_music(tmp_path):
    router = _router(tmp_path)
    assert router.route("Add what time is it to my list").skill.name == "lists"
    assert router.route("Play what time is it").skill.name == "music"


def test_clock_does_not_steal_a_document_question(tmp_path):
    route = _router(tmp_path).route("According to the document, what's the date of the meeting?")
    assert route.skill.name == "docs"


def test_router_sends_the_eval_clock_phrases_to_the_clock(tmp_path):
    for sentence in (
        "Got the time?",
        "What's the time and date?",
        "Do you know what the time is right now",
        "Which day of the week is it today",
    ):
        assert _router(tmp_path).route(sentence).skill.name == "clock"