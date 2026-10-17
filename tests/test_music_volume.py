"""More volume phrasings for the music skill, and the catch skill's music guard."""

import pytest

from friday.router.router import Router
from friday.skills.catch import CatchSkill
from friday.skills.music import Command, parse_command
from friday.skills.registry import build_registry


@pytest.mark.parametrize(
    "sentence",
    [
        "increase volume to 80%",
        "increase volume of the 80%",
        "set the volume to 80",
        "volume 80 percent",
        "turn the volume to 80%",
        "lower the volume to 80",
        "set the music volume to 80",
    ],
)
def test_volume_set_phrasings(sentence):
    assert parse_command(sentence) == Command("volume_set", value=80)


@pytest.mark.parametrize(
    ("sentence", "value"),
    [("volume full", 100), ("max volume", 100), ("set volume to maximum", 100), ("mute", 0), ("volume off", 0)],
)
def test_full_and_mute(sentence, value):
    assert parse_command(sentence) == Command("volume_set", value=value)


@pytest.mark.parametrize(
    ("sentence", "value"),
    [
        ("increase the volume", 1),
        ("raise volume", 1),
        ("turn up the volume", 1),
        ("make it louder", 1),
        ("lower the volume", -1),
        ("decrease volume", -1),
        ("turn the volume down", -1),
        ("turn it down", -1),
        ("make it quieter", -1),
    ],
)
def test_volume_direction_phrasings(sentence, value):
    assert parse_command(sentence) == Command("volume_change", value=value)


@pytest.mark.parametrize(
    ("sentence", "value"),
    [
        ("set the volume to fifty percent", 50),
        ("volume to seventy five", 75),
        ("set the volume to one hundred percent", 100),
        ("turn the volume to zero", 0),
        ("please set the volume to thirty", 30),
    ],
)
def test_volume_set_with_number_words(sentence, value):
    assert parse_command(sentence) == Command("volume_set", value=value)


def test_number_words_do_not_touch_song_titles():
    assert parse_command("play seven nation army") == Command("play", rest="seven nation army")
    assert parse_command("play fifty ways to leave your lover") == Command(
        "play", rest="fifty ways to leave your lover"
    )


@pytest.mark.parametrize(
    ("sentence", "command"),
    [
        ("it's too loud turn it down", Command("volume_change", value=-1)),
        ("it's too quiet turn it up", Command("volume_change", value=1)),
        ("that's too loud lower the volume", Command("volume_change", value=-1)),
        ("this is way too loud make it quieter", Command("volume_change", value=-1)),
        ("it's too loud can you turn it down", Command("volume_change", value=-1)),
        ("it's too loud set the volume to thirty", Command("volume_set", value=30)),
    ],
)
def test_complaint_lead_in_before_a_volume_command(sentence, command):
    assert parse_command(sentence) == command


@pytest.mark.parametrize(
    "sentence",
    [
        "it's too loud",
        "that's too loud play something quieter",
        "it's too loud skip this song",
        "it's too loud pause the music",
        "the volume of the crowd was too loud last night",
    ],
)
def test_complaint_alone_or_before_another_command_is_not_volume(sentence):
    assert parse_command(sentence) is None


@pytest.mark.parametrize(
    ("sentence", "value"),
    [
        ("make it a little quieter", -1),
        ("make it a bit louder", 1),
        ("make it a little bit quieter", -1),
        ("make it much louder", 1),
        ("make it slightly quieter", -1),
        ("a bit louder", 1),
        ("a little quieter", -1),
        ("make it a little quieter please", -1),
    ],
)
def test_volume_direction_softeners(sentence, value):
    assert parse_command(sentence) == Command("volume_change", value=value)


@pytest.mark.parametrize(
    "sentence",
    ["Make it a little quieter please", "It's too loud, turn it down", "Set the volume to fifty percent"],
)
def test_eval_phrases_reach_the_music_skill(sentence, tmp_path):
    router = Router(build_registry(None, tmp_path / "t.db", object()))
    assert router.route(sentence).skill.name == "music"


@pytest.mark.parametrize("sentence", ["I love this song", "The volume of the crowd was too loud last night"])
def test_chat_about_music_is_not_a_command(sentence, tmp_path):
    router = Router(build_registry(None, tmp_path / "t.db", object()))
    route = router.route(sentence)
    assert route.skill is None or route.skill.name != "music"


@pytest.mark.parametrize("sentence", ["if volume down", "the music", "boss the music", "awesome music"])
def test_garbled_music_is_caught(sentence):
    assert CatchSkill(reminders=False, music=True).can_handle(sentence)


@pytest.mark.parametrize(
    "sentence",
    ["one more", "tell me a joke", "how is the weather", "i was thinking about what music to put on later"],
)
def test_other_sentences_are_not_caught(sentence):
    assert not CatchSkill(reminders=False, music=True).can_handle(sentence)


def test_music_guard_is_off_without_music():
    assert not CatchSkill(reminders=False, music=False).can_handle("the music")



@pytest.mark.parametrize(
    ("sentence", "value"),
    [
        ("turn the volume down a bit", -1),
        ("turn it up a little", 1),
        ("lower the volume slightly", -1),
        ("bring the music volume down a little bit", -1),
        ("raise the volume a bit", 1),
        ("please turn it down a bit", -1),
    ],
)
def test_volume_direction_with_a_trailing_softener(sentence, value):
    assert parse_command(sentence) == Command("volume_change", value=value)


@pytest.mark.parametrize("sentence", ["volume to 30 a bit", "mute a bit", "tell me a bit"])
def test_softener_does_not_unlock_other_volume_commands(sentence):
    assert parse_command(sentence) is None


def test_softener_does_not_touch_play():
    assert parse_command("play down a bit").kind == "play"
