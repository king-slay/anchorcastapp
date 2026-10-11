"""Find a book name in transcript tokens: "First Corinthians", "Psalm", "Saint John".

Spoken names are matched in any form. Abbreviations ("Jn", "1 Cor", "Matt")
only count in the written chapter:verse form ("Jn 3:16"), because short
words like "is" or "so" followed by a number are everyday speech, and
"is 5:30" is more likely a time than Isaiah. A few book names are also
ordinary words ("job", "acts"); written in lower case they need "chapter",
"verse" or a colon after them before they count (see ``ordinary_word``).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from scripture_parser import typed_books
from scripture_parser.canon import BOOKS, BOOKS_BY_CODE, Book
from scripture_parser.tokens import Kind, Token

# Other ways to say a book, beyond its name in canon.py.
_SPOKEN: Final[dict[str, tuple[str, ...]]] = {
    "PSA": ("psalm", "psalms"),
    "SNG": ("song of songs", "songs of solomon", "canticles"),
    "ECC": ("qoheleth",),
    "NUM": ("number",),  # speech models often drop the s
    "ACT": ("acts of the apostles", "act"),
    "MAT": ("saint matthew", "st matthew"),
    "MRK": ("saint mark", "st mark"),
    "LUK": ("saint luke", "st luke"),
    "JHN": ("saint john", "st john"),
    "REV": ("revelations",),
}
_ORDINAL_PREFIX: Final = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "ii": 2, "iii": 3,
    "i": 1,  # "I Kings"; never "I John", which is far more often "I" and a name
    "fast": 1, "fist": 1,  # how tiny.en hears "first"
}  # fmt: skip
# "Fiskings", "Firstkings", "Secondchronicles": the number and name heard as one word.
_JOINED: Final = re.compile(r"(first|fist|fis|fast|1st|second|2nd|third|3rd)([a-z']+)")
_JOINED_NUMBER: Final = {"first": 1, "fist": 1, "fis": 1, "fast": 1, "1st": 1,
                         "second": 2, "2nd": 2, "third": 3, "3rd": 3}  # fmt: skip
# Numbered books heard without their final s: "First King", "2 Corinthian".
_SINGULAR: Final = {"king": "kings", "chronicle": "chronicles", "corinthian": "corinthians",
                    "thessalonian": "thessalonians", "king's": "kings"}  # fmt: skip
# Words between the number and the name: "First of Kings", "the second book of
# Samuel", "First letter to the Corinthians".
_FILLERS: Final = tuple(
    tuple(f.split())
    for f in (
        "book of the", "book of", "letter to the", "letter of", "epistle to the",
        "epistle of", "of the", "of",
    )
)  # fmt: skip
# Book names that are also everyday words, so "this job one day" is not Job 1.
_ORDINARY_WORDS: Final = frozenset({"job", "acts", "act", "mark", "numbers", "judges"})
# Words that need "chapter", "verse" or a colon even with a capital letter:
# "Number 10 verse 2" is Numbers, "Number 10." is not.
_ALWAYS_ORDINARY: Final = frozenset({"number"})
# Short words that a typed-abbreviation lookup would otherwise take for a book.
_NOT_ABBREVIATIONS: Final = frozenset(
    {"is", "so", "am", "act", "can", "at", "in", "on", "to", "me", "no", "or", "be", "do"}
)


def _names() -> dict[tuple[str, ...], Book]:
    table: dict[tuple[str, ...], Book] = {}
    for book in BOOKS:
        name = book.name.lower()
        if name[0].isdigit():
            continue  # numbered books are matched as prefix + base name
        table[tuple(name.split())] = book
    for code, variants in _SPOKEN.items():
        for variant in variants:
            table[tuple(variant.split())] = BOOKS_BY_CODE[code]
    return table


_NAMES: Final = _names()
_LONGEST_NAME: Final = max(len(key) for key in _NAMES)
# "1 Corinthians" -> ("corinthians",) -> {1: 1CO, 2: 2CO}
_NUMBERED: Final[dict[str, dict[int, Book]]] = {}
for _book in BOOKS:
    if _book.name[0].isdigit():
        _number, _base = _book.name.split(" ", 1)
        _NUMBERED.setdefault(_base.lower(), {})[int(_number)] = _book


@dataclass(frozen=True, slots=True)
class BookMatch:
    book: Book
    end: int  # index of the first token after the name
    abbreviation: bool  # needs the written chapter:verse form
    ordinary_word: bool  # a lower-case everyday word; needs chapter/verse/colon


def match_book(tokens: Sequence[Token], i: int) -> BookMatch | None:
    """The book named at ``tokens[i]``, preferring the longest name."""
    numbered = _numbered(tokens, i)
    if numbered is not None:
        return numbered
    for length in range(min(_LONGEST_NAME, len(tokens) - i), 0, -1):
        window = tokens[i : i + length]
        if any(t.kind is not Kind.WORD for t in window):
            continue
        book = _NAMES.get(tuple(t.text for t in window))
        if book is not None:
            ordinary = length == 1 and window[0].text in _ORDINARY_WORDS
            ordinary = ordinary and not window[0].capitalized
            return BookMatch(
                book, i + length, False, ordinary or window[0].text in _ALWAYS_ORDINARY
            )
    return _abbreviation(tokens, i)


def _numbered(tokens: Sequence[Token], i: int) -> BookMatch | None:
    """ "First Kings", "1st Kings", "1 Kings", and what speech models make of
    them: "First of Kings", "the first book of Kings", "Second letter to the
    Corinthians", "1-Kings", "First. Kings 3 verse 5", "Fast Kings", or the
    number after the name, "Kings 1 chapter 3"."""
    first = tokens[i]
    if first.kind is Kind.NUM:
        number = first.value
    elif first.kind is Kind.WORD and first.text in _ORDINAL_PREFIX:
        number = _ORDINAL_PREFIX[first.text]
    else:
        return _joined(tokens, i) or _number_after(tokens, i)
    j = i + 1
    if j < len(tokens) and tokens[j].kind is Kind.DASH:
        j += 1  # "1-Kings"
    elif (
        j < len(tokens)
        and tokens[j].kind is Kind.BREAK
        and (i == 0 or tokens[i - 1].kind is Kind.BREAK)
    ):
        j += 1  # "First. Kings 3": the model ended a sentence early; not "this first. John"
    for filler in _FILLERS:
        words = tokens[j : j + len(filler)]
        if len(words) == len(filler) and all(
            t.kind is Kind.WORD and t.text == w for t, w in zip(words, filler, strict=True)
        ):
            j += len(filler)
            break
    if j >= len(tokens) or tokens[j].kind is not Kind.WORD:
        return None
    base = tokens[j].text
    if first.text == "i" and (not first.capitalized or base == "john"):
        return None
    book = _NUMBERED.get(_SINGULAR.get(base, base), {}).get(number)
    if book is None:
        return None
    if j > i + 1 and not _numbers_follow(tokens, j + 1):
        return None  # a gap is only trusted when a chapter follows
    return BookMatch(book, j + 1, False, False)


def _joined(tokens: Sequence[Token], i: int) -> BookMatch | None:
    """ "Fiskings": tiny.en often writes "First Kings" as one word."""
    found = _JOINED.fullmatch(tokens[i].text) if tokens[i].kind is Kind.WORD else None
    if found is None:
        return None
    number, base = _JOINED_NUMBER[found[1]], found[2]
    book = numbered_books(base).get(number)
    return BookMatch(book, i + 1, False, False) if book is not None else None


def numbered_books(base: str) -> dict[int, Book]:
    """The numbered books with this base name: "kings" -> {1: 1KI, 2: 2KI}."""
    return _NUMBERED.get(_SINGULAR.get(base, base), {})


def _number_after(tokens: Sequence[Token], i: int) -> BookMatch | None:
    """ "Kings 1 chapter 3": the book's number after its name, only when
    "chapter" follows, so "Kings 1" alone stays chapter 1 of nothing."""
    window = tokens[i : i + 3]
    if len(window) < 3 or window[0].kind is not Kind.WORD or window[1].kind is not Kind.NUM:
        return None
    if window[2].kind is not Kind.WORD or window[2].text not in ("chapter", "chap"):
        return None
    base = _SINGULAR.get(window[0].text, window[0].text)
    book = _NUMBERED.get(base, {}).get(window[1].value)
    return BookMatch(book, i + 2, False, False) if book is not None else None


def _numbers_follow(tokens: Sequence[Token], j: int) -> bool:
    nxt = tokens[j] if j < len(tokens) else None
    if nxt is not None and nxt.kind is Kind.WORD and nxt.text in ("chapter", "chap"):
        nxt = tokens[j + 1] if j + 1 < len(tokens) else None
    return nxt is not None and nxt.kind is Kind.NUM


def _abbreviation(tokens: Sequence[Token], i: int) -> BookMatch | None:
    """A typed abbreviation, only when "chapter:verse" in digits follows."""
    for length in (2, 1):
        window = tokens[i : i + length]
        if len(window) < length or window[-1].kind is not Kind.WORD:
            continue
        if length == 2 and window[0].kind is not Kind.NUM:
            continue
        if window[-1].text in _NOT_ABBREVIATIONS:
            return None
        end = i + length
        if end < len(tokens) and tokens[end].kind is Kind.BREAK and tokens[end].text == ".":
            end += 1  # "Jn. 3:16"
        if not _written_chapter_verse(tokens, end):
            continue
        book = typed_books.find_book(" ".join(t.text for t in window))
        if book is not None:
            return BookMatch(book, end, True, False)
    return None


def _written_chapter_verse(tokens: Sequence[Token], i: int) -> bool:
    window = tokens[i : i + 3]
    return (
        len(window) == 3
        and window[0].kind is Kind.NUM
        and window[0].digits
        and window[1].kind is Kind.COLON
        and window[2].kind is Kind.NUM
        and window[2].digits
    )
