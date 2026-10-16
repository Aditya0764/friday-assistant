import pytest

from friday.voice.phrase import strip_wake_phrase


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