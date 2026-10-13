"""Music skill: play, pause, resume, skip, previous, volume, what's playing.

All the Spotify work lives in friday/spotify_client.py. This file only understands the
sentence and writes a short spoken reply, so it can be tested with a fake player.

Commands are matched on the cleaned sentence (lowercase, punctuation removed).
'play X by Y' searches Spotify; 'stop' alone is NOT music (it could mean a timer).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from friday.skills.base import Skill
from friday.spotify_client import MusicError

_POLITE_START = re.compile(r"^(?:(?:please|can you|could you|would you|will you) )+")
_POLITE_END = re.compile(r" please$")

_MEDIA = r"(?:music|song|track|spotify|playback)"
_PAUSE = re.compile(rf"^pause(?: (?:the )?{_MEDIA})?$|^stop (?:the )?{_MEDIA}$")
_RESUME = re.compile(
    rf"^(?:resume|unpause|continue)(?: (?:the )?(?:{_MEDIA}|playing))?$|^play (?:some |the )?music$"
)
_NEXT = re.compile(
    r"^skip(?: (?:this|the|that))?(?: (?:song|track))?$"
    r"|^(?:next|play the next|skip to the next|go to the next) (?:song|track)$"
)
_PREVIOUS = re.compile(
    r"^(?:previous|last|play the previous|play the last) (?:song|track)$|^go back(?: a)?(?: (?:song|track))?$"
)
_VOLUME_SET = re.compile(r"^(?:set |put |turn )?(?:the )?volume (?:to |at )?(\d{1,3})(?: ?(?:percent|%))?$")
_VOLUME_DIR = re.compile(
    r"^(?:turn |put |bring )?(?:the )?volume (up|down)$|^turn (?:the music |it )(up|down)$"
)
_LOUDER = re.compile(r"^louder$|^quieter$")
_NOW = re.compile(
    r"^what(?:'s| is) (?:this song|this track|playing|currently playing|the song playing|playing right now)$"
    r"|^what song is (?:this|playing)(?: right now)?$"
)
_PLAY = re.compile(r"^play (.+)$")


@dataclass(frozen=True)
class Command:
    kind: str  # play, resume, pause, next, previous, volume_change, volume_set, now
    rest: str = ""      # play: everything after 'play'
    title: str = ""     # play: the part before ' by '
    artist: str = ""    # play: the part after ' by '
    value: int = 0      # volume_change: +1 or -1; volume_set: percent


def parse_command(clean: str) -> Command | None:
    text = _POLITE_START.sub("", clean.strip())
    text = _POLITE_END.sub("", text)

    if _PAUSE.match(text):
        return Command("pause")
    if _RESUME.match(text):
        return Command("resume")
    if _NEXT.match(text):
        return Command("next")
    if _PREVIOUS.match(text):
        return Command("previous")
    if _NOW.match(text):
        return Command("now")
    match = _VOLUME_SET.match(text)
    if match:
        return Command("volume_set", value=int(match.group(1)))
    match = _VOLUME_DIR.match(text)
    if match:
        direction = match.group(1) or match.group(2)
        return Command("volume_change", value=1 if direction == "up" else -1)
    if text == "louder":
        return Command("volume_change", value=1)
    if text == "quieter":
        return Command("volume_change", value=-1)

    match = _PLAY.match(text)
    if match:
        rest = match.group(1)
        rest = re.sub(r" on spotify$", "", rest)
        rest = re.sub(r"^(?:me )?(?:(?:the |a )?(?:song|track)(?: called| named)? )?", "", rest).strip()
        if not rest:
            return None
        title, artist = rest, ""
        if " by " in rest:
            left, right = rest.rsplit(" by ", 1)
            if left.strip() and right.strip():
                title, artist = left.strip(), right.strip()
        return Command("play", rest=rest, title=title if artist else "", artist=artist)
    return None


class MusicSkill(Skill):
    name = "music"

    def __init__(self, player) -> None:
        self._player = player

    def can_handle(self, text: str) -> bool:
        return parse_command(text) is not None

    def run(self, args: dict[str, str]) -> str:
        command = parse_command(args.get("clean") or args["text"])
        if command is None:
            return "Sorry, I didn't catch that. Please say it again."
        try:
            return self._do(command)
        except MusicError as exc:
            return str(exc)

    def _do(self, command: Command) -> str:
        player = self._player
        if command.kind == "play":
            return f"Playing {player.play(command.rest, command.title, command.artist)}."
        if command.kind == "resume":
            player.resume()
            return "Resuming."
        if command.kind == "pause":
            player.pause()
            return "Paused."
        if command.kind == "next":
            player.next()
            return "Skipping."
        if command.kind == "previous":
            player.previous()
            return "Going back."
        if command.kind == "volume_change":
            return f"Volume {player.change_volume(command.value)} percent."
        if command.kind == "volume_set":
            return f"Volume {player.set_volume(command.value)} percent."
        playing = player.now_playing()
        return f"{playing}." if playing else "Nothing is playing."