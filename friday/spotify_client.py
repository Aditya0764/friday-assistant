"""Thin Spotify wrapper for the music skill.

Plays ONLY on the device named in .env (SPOTIFY_DEVICE_NAME). If that device is not
visible in Spotify, nothing plays. It never falls back to another device.

Login is the PKCE token saved by scripts/spotify_spike.py in .secrets/. If that saved
login stops working, we say so out loud instead of opening a browser mid conversation.
"""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

import requests
import spotipy
from dotenv import load_dotenv
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE

SCOPE = "user-modify-playback-state user-read-playback-state"
TOKEN_CACHE = Path(".secrets") / "spotify_token.json"
MIN_MATCH = 0.35  # untuned starting value: below this we say "couldn't find that"
VOLUME_STEP = 10


class MusicError(Exception):
    """A problem worth saying out loud. The message is the spoken reply."""


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _plain(a), _plain(b)).ratio()


def label(item: dict) -> str:
    """'Starboy by The Weeknd' for a Spotify track item."""
    artists = item.get("artists") or []
    if artists:
        return f"{item['name']} by {artists[0]['name']}"
    return item["name"]


def pick_best(items: list[dict], rest: str, title: str = "", artist: str = "") -> dict | None:
    """Pick the search result that best matches what was said, or None if nothing is close.

    rest is the whole phrase after 'play'. title and artist are the split on ' by ',
    which can be wrong ('stand by me'), so both readings are scored and the better wins.
    """
    best: dict | None = None
    best_score = 0.0
    for item in items:
        name = item["name"]
        names = [a["name"] for a in item.get("artists") or []]
        lead = names[0] if names else ""
        score = max(_ratio(rest, name), _ratio(rest, f"{name} {lead}"))
        if title and artist:
            artist_score = max((_ratio(artist, n) for n in names), default=0.0)
            score = max(score, 0.7 * _ratio(title, name) + 0.3 * artist_score)
        if score > best_score:
            best, best_score = item, score
    if best is None or best_score < MIN_MATCH:
        return None
    return best


class SpotifyPlayer:
    def __init__(self, client_id: str, redirect_uri: str, device_name: str,
                 cache_path: Path = TOKEN_CACHE) -> None:
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._device_name = device_name
        self._cache_path = cache_path
        self._sp: spotipy.Spotify | None = None

    @classmethod
    def from_env(cls) -> SpotifyPlayer | None:
        """Build from .env, or return None when Spotify is not set up (music skill stays off)."""
        load_dotenv()
        client_id = os.environ.get("SPOTIPY_CLIENT_ID")
        redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI")
        device_name = os.environ.get("SPOTIFY_DEVICE_NAME")
        if not (client_id and redirect_uri and device_name):
            return None
        return cls(client_id, redirect_uri, device_name)

    # --- internals -------------------------------------------------------------

    def _client(self) -> spotipy.Spotify:
        if self._sp is None:
            auth = SpotifyPKCE(
                client_id=self._client_id,
                redirect_uri=self._redirect_uri,
                scope=SCOPE,
                cache_handler=CacheFileHandler(cache_path=str(self._cache_path)),
                open_browser=False,
            )
            if auth.validate_token(auth.cache_handler.get_cached_token()) is None:
                raise MusicError(
                    "Spotify needs you to log in again. Run scripts spotify spike in the terminal."
                )
            self._sp = spotipy.Spotify(auth_manager=auth)
        return self._sp

    def _device(self, sp: spotipy.Spotify) -> dict:
        for device in sp.devices()["devices"]:
            if device["name"].lower() == self._device_name.lower():
                return device
        raise MusicError(
            f"I can't see {self._device_name} in Spotify. "
            "Open Spotify on this laptop and press play once."
        )

    def _run(self, action):
        """Run action(sp, device) and turn Spotify problems into a spoken MusicError."""
        try:
            sp = self._client()
            return action(sp, self._device(sp))
        except MusicError:
            raise
        except spotipy.SpotifyException as exc:
            if "PREMIUM" in str(exc).upper():
                raise MusicError("Spotify says playback control needs Premium.") from exc
            if exc.http_status == 404:
                raise MusicError(
                    "Spotify has no active player. Open Spotify on this laptop and press play once."
                ) from exc
            if exc.http_status == 429:
                raise MusicError("Spotify is busy. Try again in a moment.") from exc
            raise MusicError("Spotify wouldn't do that right now.") from exc
        except requests.RequestException as exc:
            raise MusicError("I can't reach Spotify right now.") from exc

    # --- what the skill calls --------------------------------------------------

    def play(self, rest: str, title: str = "", artist: str = "") -> str:
        def action(sp, device):
            items = sp.search(q=rest, type="track", limit=10)["tracks"]["items"]
            item = pick_best(items, rest, title, artist)
            if item is None:
                raise MusicError("I couldn't find that on Spotify.")
            sp.start_playback(device_id=device["id"], uris=[item["uri"]])
            return label(item)

        return self._run(action)

    def resume(self) -> None:
        self._run(lambda sp, d: sp.start_playback(device_id=d["id"]))

    def pause(self) -> None:
        self._run(lambda sp, d: sp.pause_playback(device_id=d["id"]))

    def next(self) -> None:
        self._run(lambda sp, d: sp.next_track(device_id=d["id"]))

    def previous(self) -> None:
        self._run(lambda sp, d: sp.previous_track(device_id=d["id"]))

    def change_volume(self, direction: int) -> int:
        """direction is +1 or -1. Returns the new volume percent."""
        def action(sp, device):
            now = device.get("volume_percent") or 0
            new = max(0, min(100, now + direction * VOLUME_STEP))
            sp.volume(new, device_id=device["id"])
            return new

        return self._run(action)

    def set_volume(self, percent: int) -> int:
        new = max(0, min(100, percent))
        self._run(lambda sp, d: sp.volume(new, device_id=d["id"]))
        return new

    def now_playing(self) -> str | None:
        def action(sp, device):
            current = sp.current_playback()
            if not current or not current.get("item"):
                return None
            return label(current["item"])

        return self._run(action)