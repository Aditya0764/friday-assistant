"""Slot extraction (P6-03): turn a command the rules could not parse into one they can.

The trained router says WHICH skill (lists, reminders, music). The chat LLM then fills in the
details as strict JSON (item, time, song, ...). Code checks the details, builds a plain sentence
in the exact form the skill's own parser understands ("add milk to my shopping list"), and the
skill parses and runs THAT sentence. So the LLM never acts and never speaks: it only picks
words, and a sentence the skill's rules reject becomes "please say it again".

Checks: every item, task, song, artist and list name must appear in what the user said; every
number in a time must be a number the user said; a play command needs a play-like word; the
skill must exist in this registry. Anything else returns None.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from friday.router.router import SLOT_SKILLS, normalize
from friday.skills.base import Skill, SkillRegistry
from friday.skills.calc import words_to_digits

MAX_TEXT = 80
MAX_ITEMS = 10

_LIST_NAME = re.compile(r"[a-z'-]+(?: [a-z'-]+)?")
_UNIT = r"(?:seconds?|minutes?|hours?)"
_CLOCK = r"\d{1,2}(?: \d{2})?(?: ?(?:am|pm))?"
_WHEN = {
    "reminder": re.compile(rf"(?:tomorrow )?at {_CLOCK}|in \d+ {_UNIT}"),
    "timer": re.compile(rf"\d+ {_UNIT}"),
    "alarm": re.compile(rf"(?:tomorrow )?(?:at )?{_CLOCK}"),
}
_PLAY_WORDS = re.compile(r"\b(?:play|put on|listen|hear|queue|start|stream)\b")

_LISTS_PROMPT = """You read ONE spoken command about a list or a note and reply with ONE JSON \
object and nothing else.
{"action": "add" | "remove" | "read" | "note" | "none", "items": ["..."], "list": "..."}
- add: put items on a list. remove: take ONE item off. read: say what is on a list. \
note: save a note.
- items: copy the user's own words for each item. Exactly one item for remove and note.
- list: the list's name as the user said it ("shopping", "gym", "to do"), or "" if none was named.
- Use "none" if the command is something else, or if the thing to save or remove was not said.
Example: "pop eggs onto the groceries list" -> {"action":"add","items":["eggs"],"list":"groceries"}
Example: "what is left on my gym list" -> {"action":"read","items":[],"list":"gym"}"""

_REMINDERS_PROMPT = """You read ONE spoken command about a reminder, timer or alarm and reply \
with ONE JSON object and nothing else.
{"kind": "reminder" | "timer" | "alarm" | "none", "task": "...", "when": "..."}
- reminder: task = what to be reminded about (copy the user's words). when = "at 5 pm", \
"at 7 30 am", "tomorrow at 9 am" or "in 20 minutes".
- timer: when = a count and a unit, like "10 minutes". task = "".
- alarm: when = "6 30 am" or "tomorrow at 7 am". task = "".
- Use "none" if no clear time was said or the command is something else. \
Never invent a time or a number that was not said.
Example: "nudge me at 9 pm to call mom" -> {"kind":"reminder","task":"call mom","when":"at 9 pm"}
Example: "wake me up at 6 30 am" -> {"kind":"alarm","task":"","when":"6 30 am"}"""

_MUSIC_PROMPT = """You read ONE spoken command about music and reply with ONE JSON object and \
nothing else.
{"action": "play" | "pause" | "resume" | "next" | "previous" | "now" | "none", \
"song": "...", "artist": "..."}
- play: song and artist exactly as the user said them (copy the words). Artist only if said.
- next = skip to the next song. previous = go back. now = what is playing.
- Use "none" for volume changes or anything else.
Example: "put on shape of you by ed sheeran" -> \
{"action":"play","song":"shape of you","artist":"ed sheeran"}"""

_PROMPTS = {
    "lists_notes": _LISTS_PROMPT,
    "timers_reminders": _REMINDERS_PROMPT,
    "music": _MUSIC_PROMPT,
}


def _squash(text: str) -> str:
    return re.sub(r"\bto[ -]do\b", "todo", text)


def _inside(piece: str, clean: str) -> bool:
    return f" {_squash(piece)} " in f" {_squash(clean)} "


def _text(value, clean: str, limit: int = MAX_TEXT) -> str | None:
    """A short piece of text the user really said, cleaned, or None."""
    if not isinstance(value, str):
        return None
    piece = normalize(value)
    if not piece or len(piece) > limit or not _inside(piece, clean):
        return None
    return piece


def _optional(value, clean: str) -> str | None:
    """'' stays '' (not given); anything else must pass _text."""
    if value in (None, ""):
        return ""
    return _text(value, clean)


def _digits_ok(when: str, clean: str) -> bool:
    said = set(re.findall(r"\d+", words_to_digits(clean)))
    return all(number in said for number in re.findall(r"\d+", when))


def _lists(data: dict, clean: str) -> str | None:
    action = data.get("action")
    name = _optional(data.get("list"), clean)
    if name is None or (name and not _LIST_NAME.fullmatch(name)):
        return None
    where = f"my {name} list" if name else "my list"
    if action == "read":
        return f"what's on {where}"
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        return None
    cleaned = [_text(item, clean) for item in items]
    if any(item is None for item in cleaned):
        return None
    if action == "add":
        return f"add {' and '.join(cleaned)} to {where}"
    if len(cleaned) != 1:
        return None
    if action == "remove":
        return f"remove {cleaned[0]} from {where}"
    if action == "note":
        return f"take a note {cleaned[0]}"
    return None


def _reminders(data: dict, clean: str) -> str | None:
    kind, raw_when = data.get("kind"), data.get("when")
    if kind not in _WHEN or not isinstance(raw_when, str):
        return None
    when = normalize(raw_when)
    if not _WHEN[kind].fullmatch(when) or not _digits_ok(when, clean):
        return None
    if kind == "timer":
        return f"set a timer for {when}"
    if kind == "alarm":
        return f"set an alarm for {when}"
    task = _text(data.get("task"), clean)
    return f"remind me {when} to {task}" if task else None


def _music(data: dict, clean: str) -> str | None:
    action = data.get("action")
    simple = {
        "pause": "pause the music",
        "resume": "resume the music",
        "next": "next song",
        "previous": "previous song",
        "now": "what's playing",
    }
    if action in simple:
        return simple[action]
    if action != "play" or not _PLAY_WORDS.search(clean):
        return None
    song, artist = _optional(data.get("song"), clean), _optional(data.get("artist"), clean)
    if song is None or artist is None or not (song or artist):
        return None
    return f"play {song} by {artist}" if song and artist else f"play {song or artist}"


_BUILDERS = {"lists_notes": _lists, "timers_reminders": _reminders, "music": _music}


def _parse_json(raw: str) -> dict | None:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def fill_slots(
    label: str,
    text: str,
    clean: str,
    registry: SkillRegistry,
    llm: Callable,
) -> tuple[Skill, dict[str, str]] | None:
    """(skill, args) the skill's own parser accepts, or None (then say "please say it again")."""
    skill_name = SLOT_SKILLS.get(label)
    skill = registry.get(skill_name) if skill_name else None
    if skill is None:
        return None
    try:
        reply = llm([{"role": "system", "content": _PROMPTS[label]}, {"role": "user", "content": text}])
        data = _parse_json(str(getattr(reply, "text", "") or ""))
    except Exception as exc:  # noqa: BLE001 - a failed LLM call must fall back to "say it again"
        print(f"Slot extraction failed ({type(exc).__name__}).")
        return None
    if data is None:
        return None
    sentence = _BUILDERS[label](data, clean)
    if sentence is None:
        return None
    canonical = normalize(sentence)
    if not skill.can_handle(canonical):
        return None
    return skill, {"text": sentence, "clean": canonical, "said": text}