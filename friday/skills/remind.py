"""Reminders, timers and alarms.

"Remind me at 6 to apply for jobs", "Remind me to stretch in 10 minutes",
"Set a timer for 5 minutes", "Set an alarm for 6 30 am".

"At 6" with no AM or PM means the NEXT time the clock shows 6, whichever of AM or PM
comes first. "Tomorrow at 6" with no AM or PM uses a daytime guess (7 to 11 = AM,
12 = noon, 1 to 6 = PM). The confirmation always says the full time back.
Not supported yet: repeating reminders, listing or cancelling reminders, dates beyond
tomorrow, "half an hour".
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from friday.skills.base import Skill
from friday.skills.calc import words_to_digits

MAX_DAYS = 30

_HOUR_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
               "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}  # fmt: skip
_MINUTE_WORDS = {"fifteen": "15", "thirty": "30", "forty five": "45"}
_SPOKEN_CLOCK = re.compile(
    rf"\b(?P<h>{'|'.join(_HOUR_WORDS)}) (?P<m>{'|'.join(_MINUTE_WORDS)})(?= ?(?:am|pm|a m|p m)\b)"
)


def _spoken_clock(text: str) -> str:
    """'six thirty pm' -> '6 30 pm' (otherwise the number-word step would read it as 36)."""
    return _SPOKEN_CLOCK.sub(lambda m: f"{_HOUR_WORDS[m['h']]} {_MINUTE_WORDS[m['m']]}", text)

_UNIT_SECONDS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600}
_UNIT_NAMES = {"second": "second", "sec": "second", "minute": "minute", "min": "minute",
               "hour": "hour", "hr": "hour"}  # fmt: skip
_UNIT = r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)"
_CLOCK = r"\d{1,2}(?:\s\d{2})?(?:\s?(?:am|pm|a m|p m))?"
_WHEN = rf"(?P<when>(?:tomorrow\s+)?at\s+{_CLOCK}|in\s+\d+\s*{_UNIT})"
_OPENING = r"(?:(?:can|could) you |please |hey friday |friday )?"
_START = r"(?:set a reminder|remind me|reminder)"

_REMINDER_WHEN_FIRST = re.compile(
    rf"{_OPENING}{_START}\s+{_WHEN}\s+(?:to|that|about)\s+(?P<task>.+)"
)
_REMINDER_TASK_FIRST = re.compile(
    rf"{_OPENING}{_START}\s+(?:to|that|about)\s+(?P<task>.+?)\s+{_WHEN}"
)
_TIMER = re.compile(rf"{_OPENING}(?:set |start )?(?:a |an )?timer (?:for )?(?P<n>\d+)\s*(?P<unit>{_UNIT})")
_TIMER_ALT = re.compile(
    rf"{_OPENING}(?:set |start )(?:a |an )?(?P<n>\d+)[ -]?(?P<unit>{_UNIT}) timer"
)
_ALARM = re.compile(
    rf"{_OPENING}set (?:an |a )?alarm (?:for |at )(?P<tomorrow>tomorrow\s+)?(?:at\s+)?(?P<clock>{_CLOCK})"
)
_CLOCK_PARTS = re.compile(r"(?P<h>\d{1,2})(?:\s(?P<m>\d{2}))?(?:\s?(?P<ap>am|pm|a m|p m))?")


@dataclass(frozen=True)
class Request:
    message: str  # what Friday says when it fires
    due: datetime  # timezone-aware
    confirmation: str  # what Friday says right now


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _hours(hour: int, ampm: str | None, tomorrow: bool) -> list[int] | None:
    """Possible 24-hour values for a spoken hour, or None if it is not a valid hour."""
    if hour > 23:
        return None
    if ampm:
        if not 1 <= hour <= 12:
            return None
        return [hour % 12 + (12 if ampm.startswith("p") else 0)]
    if hour in (0, *range(13, 24)):
        return [hour]
    if tomorrow:
        if 7 <= hour <= 11:
            return [hour]
        return [12 if hour == 12 else hour + 12]
    return [hour % 12, hour % 12 + 12]


def _time_text(due: datetime) -> str:
    hour = due.hour % 12 or 12
    suffix = "AM" if due.hour < 12 else "PM"
    return f"{hour}:{due.minute:02d} {suffix}" if due.minute else f"{hour} {suffix}"


def _clock_due(clock: str, tomorrow: bool, now: datetime) -> datetime | None:
    parts = _CLOCK_PARTS.fullmatch(clock)
    if parts is None:
        return None
    minute = int(parts["m"] or 0)
    hours = _hours(int(parts["h"]), parts["ap"], tomorrow)
    if hours is None or minute > 59:
        return None
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if tomorrow:
        return (midnight + timedelta(days=1)).replace(hour=hours[0], minute=minute)
    options = [midnight.replace(hour=hour, minute=minute) for hour in hours]
    ahead = [due for due in options if due > now]
    return min(ahead) if ahead else min(options) + timedelta(days=1)


def _when_due(when: str, now: datetime) -> tuple[datetime, str] | None:
    """Turn 'at 6 pm', 'tomorrow at 7' or 'in 10 minutes' into (due, spoken phrase)."""
    relative = re.fullmatch(rf"in\s+(\d+)\s*({_UNIT})", when)
    if relative:
        count, unit = int(relative[1]), relative[2].rstrip("s")
        seconds = count * _UNIT_SECONDS[unit]
        if count < 1 or seconds > MAX_DAYS * 86400:
            return None
        name = _UNIT_NAMES[unit] + ("" if count == 1 else "s")
        return now + timedelta(seconds=seconds), f"in {count} {name}"
    tomorrow = when.startswith("tomorrow")
    due = _clock_due(when.removeprefix("tomorrow").strip().removeprefix("at").strip(), tomorrow, now)
    if due is None:
        return None
    day = "tomorrow " if due.date() > now.date() else ""
    return due, f"{day}at {_time_text(due)}"


def _you(task: str) -> str:
    """Flip the pronouns so the reminder reads right when Friday says it back."""
    task = re.sub(r"\bmy\b", "your", task.removesuffix(" please").strip())
    return re.sub(r"\bme\b", "you", task)


def parse_request(clean: str, now: datetime) -> Request | None:
    """Understand a cleaned sentence as a reminder, timer or alarm, or return None."""
    text = words_to_digits(_spoken_clock(re.sub(r"(?<=[a-z])-(?=[a-z])", " ", clean)))
    text = re.sub(r"\b(in|for) an? (?=(?:seconds?|minutes?|hours?)\b)", r"\1 1 ", text)  # "in an hour"

    timer = _TIMER.fullmatch(text) or _TIMER_ALT.fullmatch(text)
    if timer:
        count, unit = int(timer["n"]), timer["unit"].rstrip("s")
        seconds = count * _UNIT_SECONDS[unit]
        if count < 1 or seconds > MAX_DAYS * 86400:
            return None
        name = _UNIT_NAMES[unit] + ("" if count == 1 else "s")
        return Request(
            message=f"Your {count} {_UNIT_NAMES[unit]} timer is done.",
            due=now + timedelta(seconds=seconds),
            confirmation=f"Okay, timer set for {count} {name}.",
        )

    alarm = _ALARM.fullmatch(text)
    if alarm:
        result = _when_due(f"{alarm['tomorrow'] or ''}at {alarm['clock']}", now)
        if result is None:
            return None
        due, phrase = result
        return Request("Your alarm is going off.", due, f"Okay, alarm set for {phrase.removeprefix('at ')}.")

    reminder = _REMINDER_WHEN_FIRST.fullmatch(text) or _REMINDER_TASK_FIRST.fullmatch(text)
    if reminder:
        result = _when_due(reminder["when"], now)
        task = _you(reminder["task"])
        if result is None or not task:
            return None
        due, phrase = result
        return Request(
            message=f"Reminder: {task}.",
            due=due,
            confirmation=f"Okay, I'll remind you to {task} {phrase}.",
        )
    return None


class ReminderSkill(Skill):
    name = "reminders"

    def __init__(self, scheduler, now_fn: Callable[[], datetime] = _local_now) -> None:
        self._scheduler = scheduler
        self._now = now_fn

    def can_handle(self, text: str) -> bool:
        return parse_request(text, self._now()) is not None

    def run(self, args: dict[str, str]) -> str:
        request = parse_request(args["clean"], self._now())
        if request is None:
            return "Sorry, I didn't catch the time."
        self._scheduler.add(request.message, request.due)
        return request.confirmation