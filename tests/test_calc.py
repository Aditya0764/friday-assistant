import pytest

from friday.router.router import Router
from friday.skills.calc import MathError, math_expression, safe_eval, words_to_digits
from friday.skills.registry import build_registry


def _answer(sentence):
    """Run a sentence through the real router and return (skill name, reply)."""
    route = Router(build_registry()).route(sentence)
    assert route.skill is not None, f"{sentence!r} was not claimed by any skill"
    return route.skill.name, route.skill.run(route.args)


# The 10 sample queries for P4-01's "done when". The first one is acceptance test A4.
SAMPLE_QUERIES = [
    ("What's 18% of 2,400?", "The answer is 432."),
    ("What is 5 plus 3?", "The answer is 8."),
    ("What's 12 times 12?", "The answer is 144."),
    ("100 divided by 8", "The answer is 12.5."),
    ("What is two hundred minus forty five?", "The answer is 155."),
    ("What's the square root of 144?", "The answer is 12."),
    ("Calculate (2 + 3) * 4", "The answer is 20."),
    ("Convert 5 km to miles.", "5 kilometers is 3.11 miles."),
    ("How many minutes are in 2 hours?", "2 hours is 120 minutes."),
    ("What is 100 degrees Fahrenheit in Celsius?", "100 degrees Fahrenheit is 37.78 degrees Celsius."),
]


@pytest.mark.parametrize(("sentence", "expected"), SAMPLE_QUERIES)
def test_sample_queries(sentence, expected):
    skill_name, reply = _answer(sentence)
    assert skill_name == "calc"
    assert reply == expected


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("What's 20 percent of 150?", "The answer is 30."),
        ("What is 2 to the power of 10?", "The answer is 1024."),
        ("What is 5 squared?", "The answer is 25."),
        ("What is 7 x 6?", "The answer is 42."),
        ("What is 10 minus 25?", "The answer is minus 15."),
        ("What is 1 divided by 3?", "The answer is 0.33."),
        ("What is 3.5 times 2?", "The answer is 7."),
        ("What is twenty-one plus one hundred and five?", "The answer is 126."),
        ("How many feet are in 3 yards?", "3 yards is 9 feet."),
        ("How many centimeters in an inch?", "1 inch is 2.54 centimeters."),
        ("Convert 2 kg to pounds", "2 kilograms is 4.41 pounds."),
        ("Convert 0 celsius to fahrenheit", "0 degrees Celsius is 32 degrees Fahrenheit."),
    ],
)
def test_more_queries(sentence, expected):
    assert _answer(sentence) == ("calc", expected)


def test_divide_by_zero_is_a_polite_answer_not_a_crash():
    assert _answer("What is 5 divided by 0?") == ("calc", "I can't divide by zero.")


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Divide 144 by 12", "The answer is 12."),
        ("divide 100 by 5", "The answer is 20."),
        ("Divide 10 by 4", "The answer is 2.5."),
        ("Please divide 144 by 12", "The answer is 12."),
        ("Divide one hundred forty four by twelve", "The answer is 12."),
        ("Divide 7 by 0", "I can't divide by zero."),
    ],
)
def test_divide_x_by_y(sentence, expected):
    assert _answer(sentence) == ("calc", expected)


@pytest.mark.parametrize(
    "sentence",
    [
        "Divide the list",
        "Divide my reminder",
        "Divide the cake by 3 people",
        "Divide 144 by 12 people",
        "Divide 10 plus 2 by 3",
        "Divide 6500 among 3 people",
        "Can you divide 144 by 12",
    ],
)
def test_divide_sentences_that_are_not_a_sum_are_not_claimed(sentence):
    route = Router(build_registry()).route(sentence)
    assert route.skill is None or route.skill.name != "calc"


def test_divide_inside_a_reminder_is_still_a_reminder():
    route = Router(build_registry(object())).route("Remind me to divide 144 by 12 at 5 pm")
    assert route.skill is not None
    assert route.skill.name == "reminders"


def test_huge_numbers_are_refused():
    assert _answer("What is 9 to the power of 99?") == ("calc", "That number is too big for me.")


@pytest.mark.parametrize(
    "sentence",
    [
        "Tell me a fun fact.",
        "What is the capital of France?",
        "I have 5 apples.",
        "Remind me at 6 to apply for jobs.",
        "Play Blinding Lights.",
        "What is 5?",
        "What is a 5-star hotel?",
        "Is 50% off a good deal?",
        "Convert 5 km to kg.",
    ],
)
def test_ordinary_sentences_are_not_claimed(sentence):
    assert Router(build_registry()).route(sentence).skill is None


def test_time_questions_still_go_to_the_clock():
    route = Router(build_registry()).route("What time is it?")
    assert route.skill is not None
    assert route.skill.name == "clock"


@pytest.mark.parametrize(
    ("words", "digits"),
    [
        ("two hundred forty five", "245"),
        ("two thousand four hundred", "2400"),
        ("one hundred and five", "105"),
        ("five and three", "5 and 3"),
        ("what is ten plus ten", "what is 10 plus 10"),
    ],
)
def test_words_to_digits(words, digits):
    assert words_to_digits(words) == digits


def test_safe_eval_rejects_anything_that_is_not_plain_math():
    for bad in ("__import__('os')", "open('x')", "[1, 2]", "1 if 1 else 2", "abs(5)"):
        with pytest.raises((MathError, SyntaxError)):
            safe_eval(bad)


def test_math_expression_returns_none_for_words():
    assert math_expression("hello friday") is None