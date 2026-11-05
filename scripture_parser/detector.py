"""Turn transcript lines into Bible references, remembering what was just said.

``Detector.hear(text)`` returns what a line refers to, using what came
before: "John chapter 3." then "Verse 16." is John 3:16; "Romans." then
"chapter 8 verse 28" is Romans 8:28. It checks every reference against the
verse counts in ``counts``, so nothing that doesn't exist is ever returned as
a verse to show.

Anything the speech model may have got wrong comes back ``flagged`` with the
reasons, for the operator to check rather than to show automatically.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from scripture_parser.canon import BOOKS_BY_CODE
from scripture_parser.commands import parse_utterance
from scripture_parser.counts import VERSES
from scripture_parser.intents import IntentType
from scripture_parser.parsed import ParsedIntent

# A book said on its own ("Romans.") or a chapter just named ("John chapter
# 3.") is used by the next bare chapter or verse for this long.
NAMED_FOR_S = 30.0
# A bare "verse 12" still belongs to the last passage this long after it was
# heard: expository preaching often returns to a chapter minutes later.
CONTEXT_FOR_S = 480.0

_WITHIN_PASSAGE = {IntentType.SELECT_VERSE, IntentType.SET_RANGE, IntentType.SELECT_CHAPTER}
_STEPS = {IntentType.NEXT_VERSE: 1, IntentType.PREVIOUS_VERSE: -1}


@dataclass(frozen=True)
class Reference:
    book: str  # USFM code: "1KI"
    chapter: int
    verse: int | None  # None: the whole chapter
    verse_end: int | None = None
    flagged: bool = False  # the operator should check it before it is shown
    reasons: tuple[str, ...] = ()
    span: tuple[int, int] = (0, 0)  # characters of the line it came from

    @property
    def name(self) -> str:
        return BOOKS_BY_CODE[self.book].name

    @property
    def label(self) -> str:
        text = f"{self.name} {self.chapter}"
        if self.verse is not None:
            text += f":{self.verse}"
            if self.verse_end not in (None, self.verse):
                text += f"-{self.verse_end}"
        return text

    def as_json(self) -> dict[str, object]:
        return {
            "book": self.name,
            "code": self.book,
            "chapter": self.chapter,
            "verse": self.verse,
            "verse_end": self.verse_end,
            "ref": self.label,
            "flagged": self.flagged,
            "reasons": list(self.reasons),
            "span": list(self.span),
        }


@dataclass(frozen=True)
class Unresolved:
    reason: str
    span: tuple[int, int] = (0, 0)

    def as_json(self) -> dict[str, object]:
        return {"unresolved": self.reason, "span": list(self.span)}


Heard = Reference | Unresolved


@dataclass
class Detector:
    clock: Callable[[], float] = time.monotonic
    _named_book: tuple[str, float] | None = None
    _named_chapter: tuple[str, int, float] | None = None
    _last: tuple[Reference, float] | None = None  # the passage in context

    def hear(self, text: str) -> list[Heard]:
        now = self.clock()
        found: list[Heard] = []
        for parsed in parse_utterance(text):
            heard = self._one(parsed, now)
            if heard is None:
                continue
            if isinstance(heard, Reference) and any(
                isinstance(f, Reference) and f.label == heard.label for f in found
            ):
                continue  # "John 1 verse 15. John 1 verse 15.": once
            found.append(heard)
            if isinstance(heard, Reference) and not heard.flagged:
                self._last = (heard, now)
        return found

    def reset(self) -> None:
        self._named_book = self._named_chapter = self._last = None

    # -- one parsed intent -------------------------------------------------

    def _one(self, parsed: ParsedIntent, now: float) -> Heard | None:
        intent = parsed.intent
        if intent is IntentType.UNRESOLVED:
            return Unresolved("; ".join(parsed.reasons) or "not understood", parsed.span)
        if intent is IntentType.NAME_BOOK and parsed.book is not None:
            self._named_book = (parsed.book, now)
            self._named_chapter = None  # a new book: the last chapter is not it
            return None
        if parsed.book is not None:
            self._named_book = None  # a full reference replaces it
            heard = _check(parsed, parsed.book, parsed.chapter)
            if (
                isinstance(heard, Reference)
                and intent is IntentType.SELECT_CHAPTER
                and not heard.flagged
            ):
                self._named_chapter = (heard.book, heard.chapter, now)
            else:
                self._named_chapter = None
            return heard
        if intent in _STEPS or intent is IntentType.RELATIVE_OFFSET:
            return self._step(parsed, now)
        if intent not in _WITHIN_PASSAGE:
            return None  # "go back", "read that again": the operator's call
        return self._within(parsed, now)

    def _within(self, parsed: ParsedIntent, now: float) -> Heard | None:
        """ "verse 16", "chapter 2 verse 7", "verses 4 to 7" with no book."""
        if self._named_chapter is not None and parsed.chapter is None:
            book, chapter, at = self._named_chapter
            if now - at <= NAMED_FOR_S and parsed.intent is not IntentType.SELECT_CHAPTER:
                return _check(parsed, book, chapter)
        if self._named_book is not None:
            book, at = self._named_book
            if now - at <= NAMED_FOR_S:
                single = BOOKS_BY_CODE[book].chapters == 1
                if parsed.chapter is None and not single:
                    # "First Kings. Verse 13": not the chapter in context,
                    # which is another book.
                    name = BOOKS_BY_CODE[book].name
                    return Unresolved(f"heard {name} but no chapter", parsed.span)
                self._named_book = None
                return _check(parsed, book, parsed.chapter or 1)
        if self._last is None or now - self._last[1] > CONTEXT_FOR_S:
            return Unresolved("no passage yet, so the book and chapter are unknown", parsed.span)
        last = self._last[0]
        chapter = parsed.chapter if parsed.chapter is not None else last.chapter
        return _check(parsed, last.book, chapter)

    def _step(self, parsed: ParsedIntent, now: float) -> Heard | None:
        if self._last is None or now - self._last[1] > CONTEXT_FOR_S:
            return None
        last = self._last[0]
        offset = parsed.offset if parsed.offset is not None else _STEPS[parsed.intent]
        verse = (last.verse_end or last.verse or 1) if offset > 0 else (last.verse or 1)
        target = replace(
            parsed,
            intent=IntentType.SET_REFERENCE,
            verse_start=verse + offset,
            verse_end=verse + offset,
        )
        return _check(target, last.book, last.chapter)


def _check(parsed: ParsedIntent, book: str, chapter: int | None) -> Heard:
    """A reference that exists, a flagged split of run-together numbers, or why not."""
    if chapter is None:
        return Unresolved("no chapter", parsed.span)
    flagged, reasons = parsed.requires_confirmation, parsed.reasons
    name = BOOKS_BY_CODE[book].name
    chapters = VERSES[book]
    start, end = parsed.verse_start, parsed.verse_end
    if not 1 <= chapter <= len(chapters):
        split = _run_together(book, chapter) if start is None and chapter >= 100 else None
        if split is None:
            return Unresolved(f"{name} {chapter} is not in the Bible", parsed.span)
        c, v = split
        why = f'heard "{chapter}" as one number; check it is {name} {c}:{v}'
        return Reference(book, c, v, v, True, (*reasons, why), parsed.span)
    last = chapters[chapter - 1]
    if start is not None and (start < 1 or (end or start) > last or (end or start) < start):
        shown = f"{start}" if end in (None, start) else f"{start}-{end}"
        return Unresolved(f"{name} {chapter}:{shown} is not in the Bible", parsed.span)
    return Reference(book, chapter, start, end, flagged, reasons, parsed.span)


def _run_together(book: str, number: int) -> tuple[int, int] | None:
    """ "John 316": one way of splitting the digits that gives a real verse."""
    digits = str(number)
    found = []
    for cut in range(1, len(digits)):
        if digits[cut] == "0":
            continue  # "1016" is not "10:016"
        c, v = int(digits[:cut]), int(digits[cut:])
        chapters = VERSES[book]
        if 1 <= c <= len(chapters) and 1 <= v <= chapters[c - 1]:
            found.append((c, v))
    return found[0] if len(found) == 1 else None
