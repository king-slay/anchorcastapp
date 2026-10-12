"""Spoken numbers: "twenty three" -> 23, "a hundred and nineteen" -> 119.

Only what a reference needs (1 to 199). Number words combine the way speech
does: tens then units, hundreds then the rest. "three sixteen" is two numbers
(3 and 16), so "John three sixteen" reads as John 3:16, while "twenty one" is
one number (21). "first", "second" and "third" are not numbers here; they
belong to book names ("First Corinthians").
"""

from collections.abc import Sequence
from typing import Final

UNITS: Final = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}  # fmt: skip
TEENS: Final = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}  # fmt: skip
TENS: Final = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip


def read_number(words: Sequence[str], start: int = 0) -> tuple[int, int] | None:
    """The number spelled out at ``words[start:]``, and how many words it took.

    ``words`` are lower-case. None if no number starts there.
    """
    i = start
    total = 0
    if _at(words, i) in UNITS and _at(words, i + 1) == "hundred":
        total = UNITS[words[i]] * 100
        i += 2
    elif _at(words, i) == "a" and _at(words, i + 1) == "hundred":
        total = 100
        i += 2
    elif _at(words, i) == "hundred":
        total = 100
        i += 1
    if total:
        # "a hundred and nineteen": "and" only belongs to the number if more follows.
        offset = 1 if _at(words, i) == "and" else 0
        rest = _below_hundred(words, i + offset)
        if rest is not None:
            value, used = rest
            return total + value, i + offset + used - start
        return total, i - start
    rest = _below_hundred(words, i)
    if rest is None:
        return None
    value, used = rest
    return value, used


def _below_hundred(words: Sequence[str], i: int) -> tuple[int, int] | None:
    word = _at(words, i)
    if word in TENS:
        unit = _at(words, i + 1)
        if unit in UNITS:
            return TENS[word] + UNITS[unit], 2
        return TENS[word], 1
    if word in TEENS:
        return TEENS[word], 1
    if word in UNITS:
        return UNITS[word], 1
    return None


def _at(words: Sequence[str], i: int) -> str | None:
    return words[i] if 0 <= i < len(words) else None
