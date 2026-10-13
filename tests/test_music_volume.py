"""More volume phrasings for the music skill, and the catch skill's music guard."""

import pytest

from friday.skills.catch import CatchSkill
from friday.skills.music import Command, parse_command


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