from datetime import datetime, timedelta, timezone

import pytest

from friday.router.router import Router, normalize
from friday.skills.registry import build_registry
from friday.skills.remind import ReminderSkill, parse_request

IST = timezone(timedelta(hours=5, minutes=30))
EVENING = datetime(2026, 10, 11, 18, 40, tzinfo=IST)  # a Sunday, 6:40 PM
AFTERNOON = datetime(2026, 10, 11, 14, 0, tzinfo=IST)


def _parse(sentence, now=EVENING):
    return parse_request(normalize(sentence), now)


def test_at_6_after_6pm_means_6am_tomorrow():
    request = _parse("Remind me at 6 to apply for jobs.")
    assert request.due == datetime(2026, 10, 12, 6, 0, tzinfo=IST)
    assert request.message == "Reminder: apply for jobs."
    assert request.confirmation == "Okay, I'll remind you to apply for jobs tomorrow at 6 AM."


def test_at_6_in_the_afternoon_means_6pm_today():
    request = _parse("Remind me at 6 to apply for jobs.", AFTERNOON)
    assert request.due == datetime(2026, 10, 11, 18, 0, tzinfo=IST)
    assert request.confirmation == "Okay, I'll remind you to apply for jobs at 6 PM."


def test_at_7_in_the_evening_means_7pm_tonight():
    request = _parse("Remind me at 7 to call home.")
    assert request.due == datetime(2026, 10, 11, 19, 0, tzinfo=IST)


def test_explicit_pm_that_has_passed_goes_to_tomorrow():
    request = _parse("Remind me at 6 pm to apply for jobs.")
    assert request.due == datetime(2026, 10, 12, 18, 0, tzinfo=IST)
    assert "tomorrow at 6 PM" in request.confirmation


@pytest.mark.parametrize(
    ("sentence", "hour", "minute"),
    [
        ("Remind me at 6:30 p.m. to eat.", 18, 30),
        ("Remind me at 6 30 pm to eat.", 18, 30),
        ("Remind me at 18:30 to eat.", 18, 30),
        ("Remind me at 9 pm to eat.", 21, 0),
        ("Remind me at 11 pm to eat.", 23, 0),
        ("Remind me at 12 am to eat.", 0, 0),
        ("Remind me at six thirty pm to eat.", 18, 30),
    ],
)
def test_clock_formats(sentence, hour, minute):
    request = _parse(sentence, AFTERNOON)
    if sentence.startswith("Remind me at 12 am"):
        assert (request.due.hour, request.due.minute) == (0, 0)
        assert request.due.date() == datetime(2026, 10, 12).date()
    else:
        assert (request.due.hour, request.due.minute) == (hour, minute)


def test_task_first_order_and_pronouns():
    request = _parse("Remind me to call my mom at 7.")
    assert request.message == "Reminder: call your mom."
    assert request.due == datetime(2026, 10, 11, 19, 0, tzinfo=IST)


def test_in_minutes():
    request = _parse("Remind me to stretch in 10 minutes.")
    assert request.due == EVENING + timedelta(minutes=10)
    assert request.confirmation == "Okay, I'll remind you to stretch in 10 minutes."


def test_in_an_hour_and_in_one_hour():
    assert _parse("Remind me to stretch in an hour.").due == EVENING + timedelta(hours=1)
    one = _parse("Remind me in one hour to stretch.")
    assert one.due == EVENING + timedelta(hours=1)
    assert one.confirmation == "Okay, I'll remind you to stretch in 1 hour."


def test_tomorrow_at_7_uses_the_morning():
    request = _parse("Remind me tomorrow at 7 to submit the form.")
    assert request.due == datetime(2026, 10, 12, 7, 0, tzinfo=IST)
    assert "tomorrow at 7 AM" in request.confirmation


@pytest.mark.parametrize(
    ("sentence", "message", "minutes", "confirmation"),
    [
        ("Set a timer for 5 minutes.", "Your 5 minute timer is done.", 5, "Okay, timer set for 5 minutes."),
        ("Start a 10 minute timer.", "Your 10 minute timer is done.", 10, "Okay, timer set for 10 minutes."),
        ("Set a 10-minute timer", "Your 10 minute timer is done.", 10, "Okay, timer set for 10 minutes."),
        ("Timer for one hour", "Your 1 hour timer is done.", 60, "Okay, timer set for 1 hour."),
        ("Set a timer for an hour", "Your 1 hour timer is done.", 60, "Okay, timer set for 1 hour."),
    ],
)
def test_timers(sentence, message, minutes, confirmation):
    request = _parse(sentence)
    assert request.message == message
    assert request.due == EVENING + timedelta(minutes=minutes)
    assert request.confirmation == confirmation


def test_alarm():
    request = _parse("Set an alarm for 6 30 am.")
    assert request.due == datetime(2026, 10, 12, 6, 30, tzinfo=IST)
    assert request.message == "Your alarm is going off."
    assert request.confirmation == "Okay, alarm set for tomorrow at 6:30 AM."


@pytest.mark.parametrize(
    "sentence",
    [
        "Remind me later.",
        "Remind me to buy milk.",
        "Remind me at 25 to do it.",
        "Remind me at 13 pm to do it.",
        "Remind me at 6 99 to do it.",
        "Set a timer.",
        "Set a timer for 0 minutes.",
        "Set a timer for 100000 hours.",
        "What is a reminder?",
        "Tell me a fun fact.",
        "Add milk to my shopping list.",
    ],
)
def test_ordinary_sentences_are_not_claimed(sentence):
    assert _parse(sentence) is None


class _FakeScheduler:
    def __init__(self):
        self.added = []

    def add(self, text, due_at):
        self.added.append((text, due_at))
        return len(self.added)


def test_skill_saves_through_the_scheduler_and_confirms():
    scheduler = _FakeScheduler()
    skill = ReminderSkill(scheduler, now_fn=lambda: AFTERNOON)
    clean = normalize("Remind me at 6 to apply for jobs.")
    assert skill.can_handle(clean)
    reply = skill.run({"text": "", "clean": clean})
    assert reply == "Okay, I'll remind you to apply for jobs at 6 PM."
    assert scheduler.added == [("Reminder: apply for jobs.", datetime(2026, 10, 11, 18, 0, tzinfo=IST))]


def test_registry_only_has_the_skill_when_a_scheduler_is_given():
    assert "reminders" not in build_registry().names()
    assert "reminders" in build_registry(_FakeScheduler()).names()


def test_routes_to_reminders_not_to_math_or_clock():
    route = Router(build_registry(_FakeScheduler())).route("Remind me at 6 to apply for jobs.")
    assert route.skill is not None
    assert route.skill.name == "reminders"


# ---------- spoken times, day parts, "wake me", "ping me" ----------

MORNING_EARLY = datetime(2026, 10, 17, 5, 0, tzinfo=IST)  # 05:00 on a Saturday
LATE_MORNING = datetime(2026, 10, 17, 10, 0, tzinfo=IST)


def _due(sentence, now=LATE_MORNING):
    request = _parse(sentence, now)
    assert request is not None, sentence
    return request


@pytest.mark.parametrize(
    ("sentence", "due", "confirmation"),
    [
        ("Remind me at five forty five to feed the cat.", (10, 17, 17, 45),
         "Okay, I'll remind you to feed the cat at 5:45 PM."),
        ("Remind me at six twenty five to stretch.", (10, 17, 18, 25),
         "Okay, I'll remind you to stretch at 6:25 PM."),
        ("Set an alarm for seven thirty tomorrow morning.", (10, 18, 7, 30),
         "Okay, alarm set for tomorrow at 7:30 AM."),
        ("Set an alarm for eight tomorrow evening.", (10, 18, 20, 0),
         "Okay, alarm set for tomorrow at 8 PM."),
        ("Set an alarm for six fifteen in the morning.", (10, 18, 6, 15),
         "Okay, alarm set for tomorrow at 6:15 AM."),
        ("Set an alarm for six thirty pm.", (10, 17, 18, 30), "Okay, alarm set for 6:30 PM."),
    ],
)
def test_spoken_clock_times_and_day_parts(sentence, due, confirmation):
    request = _due(sentence)
    assert request.due == datetime(2026, due[0], due[1], due[2], due[3], tzinfo=IST)
    assert request.confirmation == confirmation


def test_spoken_clock_joins_only_an_hour_word_and_a_minute_word():
    # "twenty five" is not an hour word, so the number-word step still reads it as 25.
    request = _due("Set a timer for twenty five minutes.")
    assert request.due == LATE_MORNING + timedelta(minutes=25)
    assert _due("Remind me to stretch in twenty five minutes.").due == LATE_MORNING + timedelta(minutes=25)


def test_spoken_clock_unit_guard_keeps_todays_reading_of_a_duration():
    # Pinned, not endorsed: with a unit after it, "six fifteen" is still ADDED by the
    # number-word step (6 + 15), so this is a 21 minute timer, as it was before the change.
    request = _due("Set a timer for six fifteen minutes.")
    assert request.due == LATE_MORNING + timedelta(minutes=21)
    assert request.confirmation == "Okay, timer set for 21 minutes."


def test_a_bare_hour_word_in_a_task_is_not_a_clock_time():
    request = _due("Remind me to call mum at five.", LATE_MORNING)
    assert request.due == datetime(2026, 10, 17, 17, 0, tzinfo=IST)
    assert _parse("Remind me to read chapter six thirty times.") is None


@pytest.mark.parametrize(
    ("sentence", "now", "due", "confirmation"),
    [
        ("Can you wake me up at seven?", LATE_MORNING, datetime(2026, 10, 18, 7, 0, tzinfo=IST),
         "Okay, alarm set for tomorrow at 7 AM."),
        ("Wake me at seven", MORNING_EARLY, datetime(2026, 10, 17, 7, 0, tzinfo=IST),
         "Okay, alarm set for 7 AM."),
        ("Please wake me up at six", LATE_MORNING, datetime(2026, 10, 18, 6, 0, tzinfo=IST),
         "Okay, alarm set for tomorrow at 6 AM."),
        ("Wake me at nine pm", LATE_MORNING, datetime(2026, 10, 17, 21, 0, tzinfo=IST),
         "Okay, alarm set for 9 PM."),
        ("Wake me at 5 45 am", LATE_MORNING, datetime(2026, 10, 18, 5, 45, tzinfo=IST),
         "Okay, alarm set for tomorrow at 5:45 AM."),
        ("Wake me up tomorrow at 8", LATE_MORNING, datetime(2026, 10, 18, 8, 0, tzinfo=IST),
         "Okay, alarm set for tomorrow at 8 AM."),
        ("Wake me up at eight in the evening", LATE_MORNING, datetime(2026, 10, 17, 20, 0, tzinfo=IST),
         "Okay, alarm set for 8 PM."),
    ],
)
def test_wake_me_bare_hour_is_am_unless_pm_is_said(sentence, now, due, confirmation):
    request = _due(sentence, now)
    assert request.due == due
    assert request.confirmation == confirmation


def test_wake_me_up_in_minutes_is_a_duration():
    request = _due("Wake me up in 20 minutes")
    assert request.due == LATE_MORNING + timedelta(minutes=20)
    assert request.confirmation == "Okay, alarm set for 20 minutes."
    assert _due("Wake me in an hour").due == LATE_MORNING + timedelta(hours=1)


@pytest.mark.parametrize("sentence", ["Wake me up when it gets light", "Wake me up", "Wake me at lunch"])
def test_wake_me_without_a_time_is_not_claimed(sentence):
    assert _parse(sentence) is None


def test_ping_me_is_a_reminder():
    request = _due("Ping me at 5 pm to leave.")
    assert request.due == datetime(2026, 10, 17, 17, 0, tzinfo=IST)
    assert request.confirmation == "Okay, I'll remind you to leave at 5 PM."
    assert _due("Can you ping me in 30 minutes to call mum").due == LATE_MORNING + timedelta(minutes=30)
    assert _parse("Ping me a good joke") is None


def test_router_sends_wake_and_ping_to_reminders():
    router = Router(build_registry(_FakeScheduler()))
    for sentence in ("Wake me up at seven", "Ping me in an hour to check the oven"):
        assert router.route(sentence).skill.name == "reminders"
