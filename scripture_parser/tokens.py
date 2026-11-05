"""Split an utterance into tokens the parser can walk, keeping where each came from.

Every token remembers its character span in the original text, so a
candidate can show the operator exactly which words it came from (§12
evidence span). Spoken numbers become number tokens here; commas and
hesitations ("uh", "um") are dropped; sentence ends (. ! ? ;) are kept
because a command must stand on its own (FR19).
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto

from scripture_parser.numbers import read_number


class Kind(Enum):
    WORD = auto()
    NUM = auto()
    COLON = auto()  # "3:16", or "3.16" typed
    DASH = auto()  # "16-18"
    BREAK = auto()  # end of a sentence


@dataclass(frozen=True, slots=True)
class Token:
    kind: Kind
    text: str  # lower case for words
    start: int
    end: int
    value: int = 0  # NUM only
    digits: bool = False  # NUM written as digits ("16"), not words ("sixteen")
    capitalized: bool = False  # WORD written with a capital ("Job", not "job")


_TOKEN = re.compile(
    r"""
    (?P<ordinal>\d+(?:st|nd|rd|th))\b
    |(?P<num>\d+)
    |(?P<word>[^\W\d_]+(?:'[^\W\d_]+)*)
    |(?P<colon>:|(?<=\d)\.(?=\d))
    |(?P<join>(?<=[^\W\d_])-(?=[^\W\d_]))
    |(?P<dash>[-\u2013\u2014])
    |(?P<brk>[.!?;])
    """,
    re.VERBOSE | re.IGNORECASE,
)
_ABBREVIATED = frozenset({"v", "vs", "vv", "chap"})
_HESITATIONS = frozenset({"uh", "um", "umm", "er", "erm", "ah", "hmm"})


def tokenize(text: str) -> list[Token]:
    text = text.replace("\u2019", "'")
    raw = list(_raw_tokens(text))
    tokens: list[Token] = []
    i = 0
    while i < len(raw):
        token = raw[i]
        if token.kind is Kind.WORD:
            words = []
            for t in raw[i:]:
                if t.kind is not Kind.WORD:
                    break
                words.append(t.text)
            number = read_number(words)
            if number is not None:
                value, used = number
                last = raw[i + used - 1]
                tokens.append(Token(Kind.NUM, str(value), token.start, last.end, value=value))
                i += used
                continue
        if token.kind is Kind.BREAK and token.text == "." and i > 0:
            previous = raw[i - 1]
            if (
                previous.kind is Kind.WORD
                and previous.text in _ABBREVIATED
                and previous.end == token.start
            ):
                i += 1  # "Mark 1 vs. 2": the dot ends an abbreviation, not a sentence
                continue
        tokens.append(token)
        i += 1
    return tokens


def _raw_tokens(text: str) -> Iterator[Token]:
    for match in _TOKEN.finditer(text):
        group = match.lastgroup
        start, end = match.span()
        if group == "num":
            yield Token(Kind.NUM, match[0], start, end, value=int(match[0]), digits=True)
        elif group in ("word", "ordinal"):
            word = match[0].lower()
            if word not in _HESITATIONS:
                yield Token(Kind.WORD, word, start, end, capitalized=match[0][0].isupper())
        elif group == "colon":
            yield Token(Kind.COLON, ":", start, end)
        elif group == "dash":
            yield Token(Kind.DASH, "-", start, end)
        elif group == "brk":
            yield Token(Kind.BREAK, match[0], start, end)
