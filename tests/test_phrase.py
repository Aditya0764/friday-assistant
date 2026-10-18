import pytest

from friday.voice.phrase import strip_wake_phrase, words_after_cut


def _words(*items):
    return tuple(items)


# "Hey Freddy, play Blinding Lights" with the wake point at 1.0 s, margin already added
HEARD = _words((" Hey", 0.2, 0.5), (" Freddy,", 0.5, 0.95), (" play", 1.1, 1.4),
               (" Blinding", 1.4, 1.8), (" Lights", 1.8, 2.2))


def test_cut_drops_misheard_wake_words_and_keeps_the_command():
    assert words_after_cut(HEARD, 1.0) == "play Blinding Lights"


def test_cut_keeps_a_word_that_straddles_the_cut():
    words = _words((" Hey", 0.2, 0.5), (" Friday,", 0.5, 0.9), (" stop", 0.95, 1.3))
    assert words_after_cut(words, 1.0) == "stop"  # starts before the cut, ends after it
    assert words_after_cut(words, 1.3) == "stop"  # ends exactly on the cut


@pytest.mark.parametrize("command", ["stop", "next", "go", "play Beautiful by Akon"])
def test_cut_keeps_short_first_words(command):
    first, *rest = command.split()
    words = [(" Hey", 0.1, 0.4), (" Freddy", 0.4, 0.9), (f" {first}", 1.05, 1.3)]
    words += [(f" {w}", 1.3 + i * 0.3, 1.6 + i * 0.3) for i, w in enumerate(rest)]
    assert words_after_cut(tuple(words), 1.0) == command


def test_cut_leaves_a_real_leading_friday_alone():
    words = _words((" Hey", 0.1, 0.4), (" Friday", 0.4, 0.9), (" Friday", 1.1, 1.5),
                   (" the", 1.5, 1.6), (" 13th", 1.6, 2.0), (" is", 2.0, 2.1),
                   (" a", 2.1, 2.2), (" movie", 2.2, 2.6))
    assert words_after_cut(words, 1.0) == "Friday the 13th is a movie"


@pytest.mark.parametrize("words", [None, ()])
def test_cut_returns_none_without_timestamps(words):
    assert words_after_cut(words, 1.0) is None


def test_cut_returns_none_when_nothing_is_left():
    assert words_after_cut(_words((" Hey", 0.1, 0.4), (" Friday", 0.4, 0.9)), 1.0) is None


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("Hey Friday, what time is it?", "what time is it?"),
        ("Friday. Add milk to my grocery list.", "Add milk to my grocery list."),
        ("hey, friday what's the time", "what's the time"),
        ("OK Friday play believer", "play believer"),
        ("what time is it?", "what time is it?"),
        ("Friday", "Friday"),
        ("Hey Friday!", "Hey Friday!"),
        ("Friday's weather", "Friday's weather"),
        ("Fridays are busy", "Fridays are busy"),
        ("I love friday nights", "I love friday nights"),
        ("He Friday. What time is it?", "What time is it?"),
    ],
)
def test_strip_wake_phrase(said, expected):
    assert strip_wake_phrase(said) == expected