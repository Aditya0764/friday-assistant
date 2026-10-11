"""Lists and notes: "Add milk to my shopping list", "What's on my shopping list?".

Everything lives in the `list_items` table. A note is just an item on the list
called "notes". A list exists as soon as it has an item.

Understood: add / put an item (or several joined by "and") on a list, read a list,
remove one item, "take a note ...", "read my notes".
Not supported yet: clearing a whole list (it needs the approval step), renaming,
numbering, quantities ("two litres of milk" is saved as typed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from friday import db
from friday.router.router import normalize
from friday.skills.base import Skill

MAX_READ = 10  # longer lists are read in part so Friday does not talk for a minute
MAX_ITEMS_PER_ADD = 10
DEFAULT_LIST = "main"

_OPENING = r"(?:(?:can|could) you |please |hey friday |friday )?"
_NAME = r"[a-z'-]+(?: [a-z'-]+)?"
_LISTREF = rf"(?: (?:my|the|our|a))?(?: (?P<list>{_NAME}))? list"
_TAIL = r"(?: please)?"

_ADD = re.compile(
    rf"{_OPENING}(?:add|put) (?P<item>.+?) (?:to|on|onto|into|in){_LISTREF}{_TAIL}"
)
_READ = re.compile(
    rf"{_OPENING}(?:what(?:'s| is) (?:on|in)|what do i have (?:on|in)"
    rf"|(?:read|show|tell|give)(?: me)?(?: what(?:'s| is) on)?(?: me)?){_LISTREF}{_TAIL}"
)
_REMOVE = re.compile(
    rf"{_OPENING}(?:remove|delete|take|cross) (?P<item>.+?) (?:from|off|off of){_LISTREF}{_TAIL}"
)
_NOTE = re.compile(
    rf"{_OPENING}(?:(?:take|make|add) a note|write down|jot down|note down)"
    rf"(?: that| to| of)? (?P<item>.+?){_TAIL}"
)
_NOTES_READ = re.compile(
    rf"{_OPENING}(?:what are|read|show|tell|give)(?: me)?(?: my| the)? notes{_TAIL}"
)


@dataclass(frozen=True)
class Action:
    kind: str  # "add", "read", "remove"
    list_name: str
    items: tuple[str, ...] = ()


def _list_name(raw: str | None) -> str:
    name = (raw or "").strip()
    name = re.sub(r"\bto[ -]do\b", "todo", name)
    name = re.sub(r"^(?:my|the|our|a) ", "", name).strip()
    return name or DEFAULT_LIST


def _split_items(raw: str) -> tuple[str, ...]:
    parts = (part.strip() for part in re.split(r"\s+and\s+", raw))
    return tuple(part for part in parts if part)[:MAX_ITEMS_PER_ADD]


def parse_action(clean: str) -> Action | None:
    """Understand a cleaned sentence as a list or note request, or return None."""
    note = _NOTE.fullmatch(clean)
    if note:
        return Action("add", "notes", (note["item"].strip(),))
    if _NOTES_READ.fullmatch(clean):
        return Action("read", "notes")
    match = _ADD.fullmatch(clean)
    if match:
        items = _split_items(match["item"])
        return Action("add", _list_name(match["list"]), items) if items else None
    match = _REMOVE.fullmatch(clean)
    if match:
        item = match["item"].strip()
        return Action("remove", _list_name(match["list"]), (item,)) if item else None
    match = _READ.fullmatch(clean)
    if match:
        return Action("read", _list_name(match["list"]))
    return None


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _where(list_name: str) -> str:
    return "your list" if list_name == DEFAULT_LIST else f"your {list_name} list"


class ListsSkill(Skill):
    name = "lists"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def can_handle(self, text: str) -> bool:
        return parse_action(text) is not None

    def run(self, args: dict[str, str]) -> str:
        # The router's clean text drops commas, so "milk, eggs and bread" would lose its
        # split. Turn spoken commas (comma + space) into "and" from the original text.
        spoken = re.sub(r",\s+", " and ", args.get("text", ""))
        action = parse_action(normalize(spoken) if spoken else args["clean"])
        if action is None:
            return "Sorry, I didn't catch that."
        conn = db.connect(self._db_path)
        try:
            if action.kind == "add":
                return self._add(conn, action)
            if action.kind == "remove":
                return self._remove(conn, action)
            return self._read(conn, action)
        finally:
            conn.close()

    def _add(self, conn, action: Action) -> str:
        have = {row["item"] for row in db.get_list_items(conn, action.list_name)}
        added, repeats = [], []
        for item in action.items:
            if item in have or item in added:
                repeats.append(item)
            else:
                db.add_list_item(conn, action.list_name, item)
                added.append(item)
        if action.list_name == "notes" and added:
            return f"Okay, noted: {_join(added)}."
        where = _where(action.list_name)
        if not added:
            return f"{_join(repeats).capitalize()} is already on {where}."
        reply = f"Okay, I added {_join(added)} to {where}."
        if repeats:
            reply += f" {_join(repeats).capitalize()} was already there."
        return reply

    def _remove(self, conn, action: Action) -> str:
        wanted = action.items[0]
        rows = db.get_list_items(conn, action.list_name)
        exact = [row for row in rows if row["item"] == wanted]
        partial = [row for row in rows if wanted in row["item"]]
        match = exact[0] if exact else (partial[0] if len(partial) == 1 else None)
        if match is None:
            return f"I couldn't find {wanted} on {_where(action.list_name)}."
        db.delete_list_item(conn, match["id"])
        return f"Okay, I removed {match['item']} from {_where(action.list_name)}."

    def _read(self, conn, action: Action) -> str:
        items = [row["item"] for row in db.get_list_items(conn, action.list_name)]
        notes = action.list_name == "notes"
        if not items:
            return "You don't have any notes yet." if notes else f"{_where(action.list_name).capitalize()} is empty."
        shown = items[:MAX_READ]
        text = _join(shown)
        if len(items) > MAX_READ:
            text += f", and {len(items) - MAX_READ} more"
        if notes:
            return f"Your notes: {text}."
        return f"On {_where(action.list_name)}: {text}."