"""Turn what an operator types for a book ("1 Cor", "Jn", "Song of Songs") into a book.

Typed forms only; the spoken forms ("First Corinthians", "Saint John") belong
to the transcript parser in M2, which can build on this.
"""

import re
from typing import Final

from scripture_parser.canon import BOOKS, BOOKS_BY_CODE, Book

# Common abbreviations that are not a unique prefix of the book's name.
_EXTRA: Final[dict[str, tuple[str, ...]]] = {
    "GEN": ("gn",),
    "LEV": ("lv",),
    "NUM": ("nm", "nb"),
    "DEU": ("dt",),
    "JDG": ("jgs",),
    "RUT": ("rt", "rth"),
    "1SA": ("1sm",),
    "2SA": ("2sm",),
    "1KI": ("1kgs", "1kg"),
    "2KI": ("2kgs", "2kg"),
    "1CH": ("1chr",),
    "2CH": ("2chr",),
    "JOB": ("jb",),
    "PSA": ("ps", "pss", "psm"),
    "PRO": ("prv",),
    "ECC": ("qoh", "qoheleth"),
    "SNG": ("songofsongs", "sos", "canticles", "canticleofcanticles"),
    "EZK": ("ezk", "ezek"),
    "DAN": ("dn",),
    "JOL": ("jl",),
    "OBA": ("ob",),
    "JON": ("jnh",),
    "MAT": ("mt",),
    "MRK": ("mk",),
    "LUK": ("lk",),
    "JHN": ("jn",),
    "ROM": ("rm",),
    "PHP": ("phil", "pp"),
    "PHM": ("phlm", "philem"),
    "JAS": ("jm",),
    "1PE": ("1pt",),
    "2PE": ("2pt",),
    "1JN": ("1jn", "1jhn"),
    "2JN": ("2jn", "2jhn"),
    "3JN": ("3jn", "3jhn"),
    "REV": ("rv", "revelations", "apocalypse"),
}

_ORDINALS: Final = {
    "1": "1", "i": "1", "1st": "1", "first": "1",
    "2": "2", "ii": "2", "2nd": "2", "second": "2",
    "3": "3", "iii": "3", "3rd": "3", "third": "3",
}  # fmt: skip
_LEADING_ORDINAL = re.compile(r"^(" + "|".join(_ORDINALS) + r")\s+(?=[a-z])")


def normalize(text: str) -> str:
    """``"1st Cor."`` -> ``"1cor"``; ``"Song of Songs"`` -> ``"songofsongs"``."""
    text = " ".join(text.lower().replace(".", " ").split())
    text = _LEADING_ORDINAL.sub(lambda m: _ORDINALS[m.group(1)] + " ", text)
    return text.replace(" ", "")


_NAMES: Final[dict[str, Book]] = {normalize(b.name): b for b in BOOKS}
_EXACT: Final[dict[str, Book]] = {
    **_NAMES,
    **{b.code.lower(): b for b in BOOKS},
    **{alias: BOOKS_BY_CODE[code] for code, aliases in _EXTRA.items() for alias in aliases},
}


def find_book(text: str) -> Book | None:
    """The book ``text`` names, or None if it names none or several."""
    key = normalize(text)
    if not key:
        return None
    if key in _EXACT:
        return _EXACT[key]
    # A unique prefix of a full name ("matt", "rev", "1 thess"). Needs at least
    # two letters so "j" or "1 j" never guesses.
    if sum(c.isalpha() for c in key) < 2:
        return None
    matches = {book.code for name, book in _NAMES.items() if name.startswith(key)}
    return BOOKS_BY_CODE[matches.pop()] if len(matches) == 1 else None
