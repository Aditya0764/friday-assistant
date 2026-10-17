"""Math and unit-conversion skill. No eval(): expressions go through a whitelist parser.

Math:        "What's 18% of 2,400?", "5 plus 3", "(2 + 3) * 4", "square root of 144",
             "two hundred minus forty five", "2 to the power of 10", "5 squared".
Conversions: "Convert 5 km to miles", "How many minutes are in 2 hours?",
             "100 degrees Fahrenheit in Celsius". Length, mass, volume, time, temperature.

can_handle only says yes when the WHOLE sentence is a clean expression or conversion,
so ordinary sentences with a number in them still go to the LLM.
Not supported yet: decimals spoken as words ("three point five"), word problems.
"""

from __future__ import annotations

import ast
import math
import operator
import re

from friday.skills.base import Skill

MAX_RESULT = 1e18
MAX_EXPONENT = 100
MAX_LENGTH = 120


class MathError(Exception):
    """A calculation that has no good answer. The message is what Friday says."""


# ---------- number words: "two hundred forty five" -> "245" ----------

_SMALL = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}  # fmt: skip
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
_SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_NUMBER_WORDS = {*_SMALL, *_TENS, *_SCALES, "hundred"}


def words_to_digits(text: str) -> str:
    """Replace runs of number words with digits. Other words are left alone."""
    tokens = text.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] not in _NUMBER_WORDS:
            out.append(tokens[i])
            i += 1
            continue
        total = current = 0
        while i < len(tokens):
            word = tokens[i]
            if word in _SMALL:
                current += _SMALL[word]
            elif word in _TENS:
                current += _TENS[word]
            elif word == "hundred":
                current = (current or 1) * 100
            elif word in _SCALES:
                total += (current or 1) * _SCALES[word]
                current = 0
            elif _is_joining_and(tokens, i):
                pass  # "one hundred AND five"
            else:
                break
            i += 1
        out.append(str(total + current))
    return " ".join(out)


def _is_joining_and(tokens: list[str], i: int) -> bool:
    return (
        tokens[i] == "and"
        and i > 0
        and (tokens[i - 1] == "hundred" or tokens[i - 1] in _SCALES)
        and i + 1 < len(tokens)
        and tokens[i + 1] in _NUMBER_WORDS
    )


# ---------- math ----------

_LEAD_INS = re.compile(
    r"^(?:what's|what is|whats|calculate|compute|work out|how much is|"
    r"can you tell me|tell me|please)\s+"
)
_WORD_OPERATORS = (
    (r"\bdivide\s+(\d+(?:\.\d+)?)\s+by\b", r"\1 / "),  # "divide 144 by 12"
    (r"\bto the power of\b", " ** "),
    (r"\bmultiplied by\b", " * "),
    (r"\bdivided by\b", " / "),
    (r"\bsquared\b", " ** 2 "),
    (r"\bcubed\b", " ** 3 "),
    (r"\btimes\b", " * "),
    (r"\bplus\b", " + "),
    (r"\bminus\b", " - "),
    (r"\bover\b", " / "),
    (r"(?<=\d)\s*x\s*(?=\d)", " * "),
    (r"\^", " ** "),
)
_EXPR_OK = re.compile(r"(?:\d+(?:\.\d+)?|\*\*|[-+*/()]|sqrt|\s)+")


def _strip_lead_ins(text: str) -> str:
    text = text.strip()
    while True:
        stripped = _LEAD_INS.sub("", text)
        if stripped == text:
            break
        text = stripped
    return text.removesuffix(" please").strip()


def math_expression(clean: str) -> str | None:
    """Turn a cleaned sentence into a plain expression, or None if it is not one."""
    if len(clean) > MAX_LENGTH:
        return None
    text = _strip_lead_ins(clean)
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)  # twenty-one -> twenty one
    text = words_to_digits(text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent)\s+of\s+", r"(\1 / 100) * ", text)
    text = re.sub(r"\b(?:the\s+)?square root of\s+(\d+(?:\.\d+)?)", r"sqrt(\1)", text)
    for pattern, replacement in _WORD_OPERATORS:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s+", " ", text).strip()
    if not _EXPR_OK.fullmatch(text):
        return None
    if not re.search(r"\d", text) or not re.search(r"[-+*/]|sqrt", text):
        return None
    try:
        ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    return text


_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _too_big(value: float) -> bool:
    return abs(value) > MAX_RESULT


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise MathError("That number is too big for me.")
        result = _BINARY[type(node.op)](left, right)
        if isinstance(result, complex):
            raise MathError("I can't work that one out.")
        if _too_big(result):
            raise MathError("That number is too big for me.")
        return result
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sqrt"
        and len(node.args) == 1
        and not node.keywords
    ):
        value = _eval(node.args[0])
        if value < 0:
            raise MathError("I can't take the square root of a negative number.")
        return math.sqrt(value)
    raise MathError("I can't work that one out.")


def safe_eval(expression: str) -> float:
    """Evaluate a whitelisted expression. Raises MathError for bad or huge results."""
    try:
        return _eval(ast.parse(expression, mode="eval"))
    except ZeroDivisionError as exc:
        raise MathError("I can't divide by zero.") from exc
    except (OverflowError, RecursionError) as exc:
        raise MathError("That number is too big for me.") from exc


def spoken_number(value: float) -> str:
    """432.0 -> '432', 12.5 -> '12.5', 1/3 -> '0.33', -2 -> 'minus 2'."""
    if value < 0:
        return "minus " + spoken_number(-value)
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


# ---------- unit conversion ----------

# canonical: (category, factor to the base unit, singular name, plural name, spoken aliases)
_UNITS: dict[str, tuple[str, float, str, str, tuple[str, ...]]] = {
    "km": ("length", 1000.0, "kilometer", "kilometers",
           ("km", "kms", "kilometer", "kilometers", "kilometre", "kilometres")),
    "m": ("length", 1.0, "meter", "meters", ("m", "meter", "meters", "metre", "metres")),
    "cm": ("length", 0.01, "centimeter", "centimeters",
           ("cm", "centimeter", "centimeters", "centimetre", "centimetres")),
    "mm": ("length", 0.001, "millimeter", "millimeters",
           ("mm", "millimeter", "millimeters", "millimetre", "millimetres")),
    "mile": ("length", 1609.344, "mile", "miles", ("mile", "miles", "mi")),
    "yard": ("length", 0.9144, "yard", "yards", ("yard", "yards", "yd", "yds")),
    "foot": ("length", 0.3048, "foot", "feet", ("foot", "feet", "ft")),
    "inch": ("length", 0.0254, "inch", "inches", ("inch", "inches")),
    "kg": ("mass", 1.0, "kilogram", "kilograms",
           ("kg", "kgs", "kilogram", "kilograms", "kilo", "kilos")),
    "g": ("mass", 0.001, "gram", "grams", ("g", "gram", "grams")),
    "lb": ("mass", 0.45359237, "pound", "pounds", ("lb", "lbs", "pound", "pounds")),
    "oz": ("mass", 0.028349523125, "ounce", "ounces", ("oz", "ounce", "ounces")),
    "l": ("volume", 1.0, "liter", "liters", ("l", "liter", "liters", "litre", "litres")),
    "ml": ("volume", 0.001, "milliliter", "milliliters",
           ("ml", "milliliter", "milliliters", "millilitre", "millilitres")),
    "second": ("time", 1.0, "second", "seconds", ("second", "seconds", "sec", "secs")),
    "minute": ("time", 60.0, "minute", "minutes", ("minute", "minutes", "min", "mins")),
    "hour": ("time", 3600.0, "hour", "hours", ("hour", "hours", "hr", "hrs")),
    "day": ("time", 86400.0, "day", "days", ("day", "days")),
    "week": ("time", 604800.0, "week", "weeks", ("week", "weeks")),
    "c": ("temperature", 0.0, "degree Celsius", "degrees Celsius", ("c", "celsius", "centigrade")),
    "f": ("temperature", 0.0, "degree Fahrenheit", "degrees Fahrenheit", ("f", "fahrenheit")),
    "k": ("temperature", 0.0, "kelvin", "kelvin", ("k", "kelvin")),
}  # fmt: skip
_ALIASES = {alias: key for key, spec in _UNITS.items() for alias in spec[4]}

_NUM = r"(-?\d+(?:\.\d+)?|an?)"
_CONVERT = re.compile(rf"(?:convert\s+)?{_NUM}\s*([a-z]+)\s+(?:to|in|into)\s+([a-z]+)")
_HOW_MANY = re.compile(
    rf"how (?:many|much)\s+([a-z]+)\s+(?:are\s+|is\s+)?(?:in|there in)\s+{_NUM}\s*([a-z]+)"
)


def _to_celsius(value: float, unit: str) -> float:
    if unit == "f":
        return (value - 32) * 5 / 9
    if unit == "k":
        return value - 273.15
    return value


def _from_celsius(value: float, unit: str) -> float:
    if unit == "f":
        return value * 9 / 5 + 32
    if unit == "k":
        return value + 273.15
    return value


def convert(value: float, source: str, target: str) -> float:
    """Convert between two canonical unit keys of the same category."""
    if _UNITS[source][0] == "temperature":
        return _from_celsius(_to_celsius(value, source), target)
    return value * _UNITS[source][1] / _UNITS[target][1]


def parse_conversion(clean: str) -> tuple[float, str, str] | None:
    """Return (value, source key, target key) if the sentence is a conversion."""
    if len(clean) > MAX_LENGTH:
        return None
    text = _strip_lead_ins(clean)
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)
    text = words_to_digits(text)
    text = re.sub(r"\bdegrees?\s+", "", text)
    if match := _HOW_MANY.fullmatch(text):
        target_word, number, source_word = match.groups()
    elif match := _CONVERT.fullmatch(text):
        number, source_word, target_word = match.groups()
    else:
        return None
    source, target = _ALIASES.get(source_word), _ALIASES.get(target_word)
    if source is None or target is None or _UNITS[source][0] != _UNITS[target][0]:
        return None
    value = 1.0 if number in ("a", "an") else float(number)
    return value, source, target


def _unit_name(key: str, value: float) -> str:
    _category, _factor, singular, plural, _aliases = _UNITS[key]
    return singular if value == 1 else plural


class CalcSkill(Skill):
    name = "calc"

    def can_handle(self, text: str) -> bool:
        return parse_conversion(text) is not None or math_expression(text) is not None

    def run(self, args: dict[str, str]) -> str:
        clean = args["clean"]
        conversion = parse_conversion(clean)
        if conversion is not None:
            value, source, target = conversion
            result = convert(value, source, target)
            return (
                f"{spoken_number(value)} {_unit_name(source, value)} is "
                f"{spoken_number(result)} {_unit_name(target, round(result, 2))}."
            )
        expression = math_expression(clean)
        if expression is None:
            return "I can't work that one out."
        try:
            return f"The answer is {spoken_number(safe_eval(expression))}."
        except MathError as exc:
            return str(exc)