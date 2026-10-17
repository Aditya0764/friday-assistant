"""Tests for the music skill and the Spotify wrapper. No network: Spotify is faked."""

import pytest

from friday.router.router import Router
from friday.skills.music import Command, MusicSkill, parse_command
from friday.skills.registry import build_registry
from friday.spotify_client import MusicError, SpotifyPlayer, pick_best

ITEMS = [
    {"name": "Starboy", "uri": "u2", "artists": [{"name": "The Weeknd"}, {"name": "Daft Punk"}]},
    {"name": "Blinding Lights", "uri": "u1", "artists": [{"name": "The Weeknd"}]},
    {"name": "Save Your Tears", "uri": "u3", "artists": [{"name": "The Weeknd"}]},
]


# --- parsing -----------------------------------------------------------------------------


def test_play_with_artist():
    assert parse_command("play starboy by the weeknd") == Command(
        "play", rest="starboy by the weeknd", title="starboy", artist="the weeknd"
    )


def test_play_title_only():
    assert parse_command("play starboy") == Command("play", rest="starboy")


def test_polite_and_song_word():
    assert parse_command("please play the song starboy") == Command("play", rest="starboy")
    assert parse_command("can you play blinding lights please") == Command("play", rest="blinding lights")


def test_by_inside_a_title_keeps_the_whole_phrase():
    command = parse_command("play stand by me")
    assert command.rest == "stand by me"


@pytest.mark.parametrize(
    ("sentence", "kind"),
    [
        ("pause", "pause"),
        ("pause the music", "pause"),
        ("stop the music", "pause"),
        ("resume", "resume"),
        ("continue the music", "resume"),
        ("play music", "resume"),
        ("play some music", "resume"),
        ("skip", "next"),
        ("skip this song", "next"),
        ("next song", "next"),
        ("previous song", "previous"),
        ("go back", "previous"),
        ("what's playing", "now"),
        ("what song is this", "now"),
    ],
)
def test_simple_commands(sentence, kind):
    assert parse_command(sentence).kind == kind


@pytest.mark.parametrize(
    ("sentence", "value"),
    [("volume up", 1), ("turn the volume down", -1), ("turn it up", 1), ("louder", 1), ("quieter", -1)],
)
def test_volume_direction(sentence, value):
    assert parse_command(sentence) == Command("volume_change", value=value)


def test_volume_set():
    assert parse_command("set volume to 40") == Command("volume_set", value=40)
    assert parse_command("volume 50%") == Command("volume_set", value=50)


@pytest.mark.parametrize(
    "sentence",
    ["what time is it", "play", "tell me a joke", "add milk to my shopping list", "what is 5 plus 5"],
)
def test_not_music(sentence):
    assert parse_command(sentence) is None


@pytest.mark.parametrize(
    "sentence", ["stop", "stop it", "stop playing", "please stop", "stop please", "can you stop"]
)
def test_bare_stop_pauses(sentence):
    assert parse_command(sentence) == Command("pause")


@pytest.mark.parametrize(
    "sentence", ["stop the timer", "stop talking", "stop reading", "stop making jokes"]
)
def test_stop_with_something_else_is_not_music(sentence):
    assert parse_command(sentence) is None


# --- the skill, with a fake player ---------------------------------------------------------


class FakePlayer:
    def __init__(self):
        self.calls = []
        self.volume = 50
        self.playing = "Starboy by The Weeknd"

    def play(self, rest, title="", artist=""):
        self.calls.append(("play", rest, title, artist))
        return "Starboy by The Weeknd"

    def resume(self):
        self.calls.append("resume")

    def pause(self):
        self.calls.append("pause")

    def next(self):
        self.calls.append("next")

    def previous(self):
        self.calls.append("previous")

    def change_volume(self, direction):
        self.volume += direction * 10
        return self.volume

    def set_volume(self, percent):
        self.volume = percent
        return percent

    def now_playing(self):
        return self.playing


def run(skill, sentence):
    return skill.run({"text": sentence, "clean": sentence.lower()})


def test_replies():
    player = FakePlayer()
    skill = MusicSkill(player)
    assert run(skill, "play starboy") == "Playing Starboy by The Weeknd."
    assert run(skill, "pause") == "Paused."
    assert run(skill, "resume") == "Resuming."
    assert run(skill, "skip") == "Skipping."
    assert run(skill, "previous song") == "Going back."
    assert run(skill, "volume up") == "Volume 60 percent."
    assert run(skill, "set volume to 40") == "Volume 40 percent."
    assert run(skill, "what's playing") == "Starboy by The Weeknd."
    assert player.calls[0] == ("play", "starboy", "", "")


def test_nothing_playing():
    player = FakePlayer()
    player.playing = None
    assert run(MusicSkill(player), "what's playing") == "Nothing is playing."


def test_music_error_is_spoken():
    class Broken(FakePlayer):
        def play(self, rest, title="", artist=""):
            raise MusicError("I couldn't find that on Spotify.")

    assert run(MusicSkill(Broken()), "play zzzz") == "I couldn't find that on Spotify."


# --- search matching -----------------------------------------------------------------------


def test_pick_best_does_not_just_take_the_first_result():
    assert pick_best(ITEMS, "blinding lights")["uri"] == "u1"


def test_pick_best_uses_title_and_artist():
    best = pick_best(ITEMS, "save your tears by the weeknd", "save your tears", "the weeknd")
    assert best["uri"] == "u3"


def test_pick_best_none_when_nothing_close():
    assert pick_best(ITEMS, "zzzzqqqq") is None
    assert pick_best([], "anything") is None


def test_pick_best_title_with_by_inside():
    items = [{"name": "Stand By Me", "uri": "s1", "artists": [{"name": "Ben E. King"}]}]
    assert pick_best(items, "stand by me", "stand", "me")["uri"] == "s1"


# --- the device safety rule ----------------------------------------------------------------


class FakeSp:
    def __init__(self, devices):
        self._devices = devices
        self.started = []
        self.volumes = []

    def devices(self):
        return {"devices": self._devices}

    def search(self, q, type, limit):
        return {"tracks": {"items": ITEMS}}

    def start_playback(self, device_id=None, uris=None):
        self.started.append((device_id, uris))

    def volume(self, percent, device_id=None):
        self.volumes.append((percent, device_id))


def make_player(sp):
    player = SpotifyPlayer("client", "http://127.0.0.1:8888/callback", "ADI7")
    player._sp = sp  # skip the real login
    return player


def test_never_plays_on_another_device():
    sp = FakeSp([{"name": "Hall speaker", "id": "h1"}])
    with pytest.raises(MusicError, match="ADI7"):
        make_player(sp).play("blinding lights")
    assert sp.started == []


def test_plays_only_on_the_named_device():
    sp = FakeSp([{"name": "Hall speaker", "id": "h1"}, {"name": "adi7", "id": "a1", "volume_percent": 50}])
    assert make_player(sp).play("blinding lights") == "Blinding Lights by The Weeknd"
    assert sp.started == [("a1", ["u1"])]


def test_volume_is_clamped():
    sp = FakeSp([{"name": "ADI7", "id": "a1", "volume_percent": 95}])
    player = make_player(sp)
    assert player.change_volume(1) == 100
    assert player.set_volume(250) == 100
    assert sp.volumes == [(100, "a1"), (100, "a1")]


# --- registry ------------------------------------------------------------------------------


def test_registry_order(tmp_path):
    registry = build_registry(None, tmp_path / "t.db", FakePlayer())
    assert "music" in registry.names()
    assert registry.names()[-1] == "catch"


def test_registry_without_player_has_no_music(tmp_path):
    assert "music" not in build_registry(None, tmp_path / "t.db").names()


def test_router_sends_play_to_music(tmp_path):
    router = Router(build_registry(None, tmp_path / "t.db", FakePlayer()))
    assert router.route("Play Starboy by The Weeknd.").skill.name == "music"
    assert router.route("Pause the music.").skill.name == "music"


def test_router_stop_is_music_only_when_music_is_on(tmp_path):
    with_music = Router(build_registry(None, tmp_path / "t.db", FakePlayer()))
    assert with_music.route("Stop.").skill.name == "music"
    without_music = Router(build_registry(None, tmp_path / "t2.db"))
    assert without_music.route("Stop.").skill is None


def test_stop_pauses_the_player():
    player = FakePlayer()
    assert run(MusicSkill(player), "stop") == "Paused."
    assert player.calls == ["pause"]