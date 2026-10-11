from datetime import datetime

from friday.router.router import normalize
from friday.skills.clock import ClockSkill

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