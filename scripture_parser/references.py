"""Explicit references in a transcript, with ranges and corrections (FR07, FR08, FR17).

Handles the shapes people say and type:

- "Isaiah chapter five verse seven", "Isaiah five seven", "Isaiah 5:7"
- "First Corinthians thirteen verse four", "1 Cor 13:4-7"
- "Psalm twenty three" (a chapter; no verse is inferred, FR08)
- "Romans eight verses twenty eight to thirty", "verses 28 and 29",
  "chapter 13, from verses 4 to 7"
- "Jude three" (one-chapter books take the number as the verse)
- several references in one utterance, in the order spoken
- "John three sixteen, sorry, verse seventeen" -> one corrected John 3:17
- "turn to the book of Romans." -> the book alone (NAME_BOOK), for the
  chapter said next

Nothing here checks the database; ``validation`` does that.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final

from scripture_parser.canon import Book
from scripture_parser.intents import IntentType
from scripture_parser.parsed import ParsedIntent
from scripture_parser.spoken_books import match_book, numbered_books
from scripture_parser.tokens import Kind, Token

CHAPTER_WORDS: Final = frozenset({"chapter", "chapters", "chap"})
VERSE_WORDS: Final = frozenset({"verse", "verses", "v", "vs", "vv"})
RANGE_WORDS: Final = frozenset({"to", "through", "thru", "till", "until"})
_ALONE_LEAD_INS: Final = frozenset({"and", "okay", "ok", "now", "so", "then", "in", "to"})
_SOUNDS_LIKE: Final = {"to": 2, "too": 2, "for": 4}
_GO_VERBS: Final = frozenset({"turn", "go", "open", "flip", "come", "move", "look"})
_CORRECTIONS: Final = (
    ("i", "mean"),
    ("i", "meant"),
    ("make", "that"),
    ("or", "rather"),
    ("sorry",),
    ("correction",),
    ("rather",),
    ("pardon",),
)
CROSS_CHAPTER = "a range across chapters is not supported; pick each chapter on its own"


@dataclass(frozen=True, slots=True)
class FoundReference:
    parsed: ParsedIntent
    tokens: range  # indices of the tokens it used


@dataclass
class _Cursor:
    tokens: Sequence[Token]
    i: int

    def peek(self) -> Token | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def word(self, options: frozenset[str] | set[str]) -> bool:
        token = self.peek()
        if token is not None and token.kind is Kind.WORD and token.text in options:
            self.i += 1
            return True
        return False

    def kind(self, kind: Kind) -> bool:
        token = self.peek()
        if token is not None and token.kind is kind:
            self.i += 1
            return True
        return False

    def num(self) -> int | None:
        token = self.peek()
        if token is not None and token.kind is Kind.NUM:
            self.i += 1
            return token.value
        return None

    def end_char(self) -> int:
        return self.tokens[self.i - 1].end


@dataclass(frozen=True, slots=True)
class _Numbers:
    """The chapter and verse part of a reference or a fragment of one."""

    chapter: int | None
    start: int | None
    end: int | None
    marked: bool = False  # "chapter", "verse" or ":" was said
    cross_chapter: bool = False
    bare: bool = False  # a lone number after a correction: "sorry, seventeen"


def find_references(tokens: Sequence[Token]) -> list[FoundReference]:
    """Every explicit reference in ``tokens``, in the order spoken."""
    found: list[FoundReference] = []
    i = 0
    while i < len(tokens):
        hit = _reference_at(tokens, i)
        if hit is None:
            which = _which_numbered(tokens, i)
            if which:
                found.extend(FoundReference(p, range(i, which[1])) for p in which[0])
                i = which[1]
                continue
            alone = _book_alone(tokens, i)
            if alone is not None:
                found.append(FoundReference(alone[0], range(i, alone[1])))
                i = alone[1]
            else:
                i += 1
            continue
        parsed, end = hit
        first = i
        while True:
            corrected = _correction(tokens, end, parsed)
            if corrected is not None:
                parsed, end = corrected
                continue
            extra = _and_more(tokens, end, parsed)
            if extra is not None:
                found.append(FoundReference(parsed, range(first, end)))
                first = end
                parsed, end = extra
                continue
            break
        found.append(FoundReference(parsed, range(first, end)))
        i = end
    return found


def read_verses(c: _Cursor, *, bare: bool) -> tuple[int, int, bool, int | None] | None:
    """``verse 7``, ``:7`` or (if ``bare``) ``7``, then an optional range.

    Returns (start, end, marked, end_chapter); ``end_chapter`` is set when the
    range runs into another chapter ("3:16 to 4:2").
    """
    save = c.i
    marked = True
    if c.kind(Kind.COLON):
        start = c.num()
    elif c.word(VERSE_WORDS):
        c.word({"from"})  # "verses from 4 to 7"
        start = c.num()
    else:
        if c.word({"and", "from"}) and c.word(VERSE_WORDS):  # "chapter 13, from verses 4"
            c.word({"from"})
            start = c.num()
        else:
            c.i = save
            start = c.num() if bare else None
            marked = False
    if start is None:
        c.i = save
        return None
    end = start
    end_chapter = None
    save = c.i
    if c.kind(Kind.DASH) or c.word(RANGE_WORDS):
        c.word(VERSE_WORDS)
        number = c.num()
        if number is None:
            c.i = save
        else:
            after = c.i
            verse = c.num() if c.kind(Kind.COLON) else None
            if verse is not None:
                end_chapter, end = number, verse
            else:
                c.i = after
                end = number
    elif c.word({"and"}):
        c.word(VERSE_WORDS)
        number = c.num()
        if number is not None and number == end + 1:
            end = number
        else:
            c.i = save  # "verses 3 and 7" are two references; see _and_more
    return start, end, marked, end_chapter


def _reference_at(tokens: Sequence[Token], i: int) -> tuple[ParsedIntent, int] | None:
    match = match_book(tokens, i)
    if match is None:
        return None
    c = _Cursor(tokens, match.end)
    numbers = _after_book(c, match.book)
    if numbers is None or (match.ordinary_word and not numbers.marked):
        return None
    span = (tokens[i].start, c.end_char())
    return _intent(match.book.code, numbers, span), c.i


def _which_numbered(tokens: Sequence[Token], i: int) -> tuple[list[ParsedIntent], int] | None:
    """ "Kings, chapter 1, verse 1": speech models often drop the "First" or
    "Second". Suggest each book with that name, flagged, for the operator to
    pick; only when "chapter" follows, so "the kings of the earth" is not one."""
    token = tokens[i]
    books = numbered_books(token.text) if token.kind is Kind.WORD else {}
    if not books or not _is_word(tokens, i + 1, "chapter"):
        return None
    reason = f'heard "{token.text.capitalize()}" without First or Second; check which book'
    found = []
    end = i + 1
    for book in books.values():
        c = _Cursor(tokens, i + 1)
        numbers = _after_book(c, book)
        if numbers is None or numbers.cross_chapter:
            return None
        parsed = _intent(book.code, numbers, (token.start, c.end_char()))
        found.append(replace(parsed, requires_confirmation=True, reasons=(reason,)))
        end = c.i
    return found, end


def _book_alone(tokens: Sequence[Token], i: int) -> tuple[ParsedIntent, int] | None:
    """A book named with no chapter, at the end of a sentence, where the
    words before it show the speaker is going there: "the book of Romans",
    "the book called Philemon", "turn with me to Romans", or "Isaiah." as a
    sentence on its own. Just "Romans" in passing ("as Paul told the Romans")
    is not enough."""
    match = match_book(tokens, i)
    if match is None or match.ordinary_word or match.abbreviation:
        return None
    if match.end < len(tokens) and tokens[match.end].kind is not Kind.BREAK:
        return None
    before = []
    for token in reversed(tokens[:i]):
        if token.kind is Kind.BREAK:
            break
        before.append(token.text)
    before.reverse()
    named = before[-2:] in (["book", "of"], ["book", "called"], ["book", "named"])
    going = bool(before) and before[-1] == "to" and not _GO_VERBS.isdisjoint(before)
    alone = _ALONE_LEAD_INS.issuperset(before)  # "Isaiah." as a sentence of its own
    if not (named or going or alone):
        return None
    span = (tokens[i].start, tokens[match.end - 1].end)
    return ParsedIntent(IntentType.NAME_BOOK, span, book=match.book.code), match.end


def _after_book(c: _Cursor, book: Book) -> _Numbers | None:
    marked = c.word(CHAPTER_WORDS)
    single = book.chapters == 1
    token = c.peek()
    if single and token is not None and token.kind is Kind.WORD and token.text in VERSE_WORDS:
        chapter = 1  # "Jude verse three"
    else:
        number = c.num()
        if number is None:
            number = _misheard_number(c)
        if number is None:
            return None
        chapter = number
    verses = read_verses(c, bare=True)
    if verses is None:
        if single and not marked:
            return _Numbers(1, chapter, chapter)  # "Jude three"
        return _Numbers(chapter, None, None, marked)
    start, end, verse_marked, end_chapter = verses
    return _Numbers(
        chapter, start, end, marked or verse_marked, cross_chapter=end_chapter is not None
    )


def _misheard_number(c: _Cursor) -> int | None:
    """ "Acts to verse 3": speech models write the chapter "two" or "four" as
    the word it sounds like. Only trusted right before "verse"."""
    token = c.peek()
    after = c.tokens[c.i + 1] if c.i + 1 < len(c.tokens) else None
    if token is None or token.kind is not Kind.WORD or token.text not in _SOUNDS_LIKE:
        return None
    if after is None or after.kind is not Kind.WORD or after.text not in VERSE_WORDS:
        return None
    c.i += 1
    return _SOUNDS_LIKE[token.text]


def _fragment(c: _Cursor) -> _Numbers | None:
    """A reference without its book: "chapter four", "verse seventeen",
    "4:2", or a lone number."""
    save = c.i
    if c.word(CHAPTER_WORDS):
        chapter = c.num()
        if chapter is None:
            c.i = save
            return None
        verses = read_verses(c, bare=True)
        if verses is None:
            return _Numbers(chapter, None, None, True)
        start, end, _, end_chapter = verses
        return _Numbers(chapter, start, end, True, cross_chapter=end_chapter is not None)
    token = c.peek()
    if token is not None and token.kind is Kind.WORD and token.text in VERSE_WORDS:
        verses = read_verses(c, bare=False)
        if verses is None:
            return None
        start, end, _, end_chapter = verses
        return _Numbers(None, start, end, True, cross_chapter=end_chapter is not None)
    number = c.num()
    if number is None:
        return None
    if (token := c.peek()) is not None and token.kind is Kind.COLON:
        verses = read_verses(c, bare=False)  # "4:2"
        if verses is not None:
            start, end, _, end_chapter = verses
            return _Numbers(number, start, end, True, cross_chapter=end_chapter is not None)
    end = number
    after = c.i
    if c.kind(Kind.DASH) or c.word(RANGE_WORDS):
        last = c.num()
        if last is None:
            c.i = after
        else:
            end = last
    # A lone number only counts if it ends the sentence: "I mean seventeen",
    # not "sorry, one more thing" or "and 17 people".
    if (token := c.peek()) is not None and token.kind is not Kind.BREAK:
        c.i = save
        return None
    return _Numbers(None, number, end, bare=True)


def _correction(
    tokens: Sequence[Token], end: int, previous: ParsedIntent
) -> tuple[ParsedIntent, int] | None:
    """A correction straight after a reference replaces it (FR17)."""
    c = _Cursor(tokens, end)
    _skip_breaks(c)
    said = False
    while _correction_word(c):
        said = True
        _skip_breaks(c)
    if not said:
        return None
    full = _reference_at(tokens, c.i)
    if full is not None:
        new, after = full
        return replace(new, span=(previous.span[0], new.span[1]), corrected_from=previous), after
    fragment = _fragment(c)
    if fragment is None:
        return None
    merged = _merge(previous, fragment, (previous.span[0], c.end_char()))
    return replace(merged, corrected_from=previous), c.i


def _and_more(
    tokens: Sequence[Token], end: int, previous: ParsedIntent
) -> tuple[ParsedIntent, int] | None:
    """ "John 3:16 and verse 18", "Psalm 23 and 24": another reference in
    the same book."""
    c = _Cursor(tokens, end)
    if previous.intent is IntentType.UNRESOLVED or not c.word({"and"}):
        return None
    start = c.peek()
    fragment = _fragment(c)
    if fragment is None or start is None:
        return None
    return _merge(previous, fragment, (start.start, c.end_char())), c.i


def _merge(previous: ParsedIntent, fragment: _Numbers, span: tuple[int, int]) -> ParsedIntent:
    """Apply a fragment to the reference before it. A chapter replaces the
    chapter and verses; a verse replaces the verses; a lone number replaces
    the finest part the reference had."""
    if previous.book is None or previous.chapter is None:
        raise ValueError("a fragment needs a complete reference before it")
    if fragment.chapter is not None:
        numbers = fragment
    elif fragment.bare and previous.verse_start is None and fragment.start == fragment.end:
        numbers = _Numbers(fragment.start, None, None)
    else:
        numbers = replace(fragment, chapter=previous.chapter)
    return _intent(previous.book, numbers, span)


def _intent(book: str, numbers: _Numbers, span: tuple[int, int]) -> ParsedIntent:
    if numbers.cross_chapter:
        return ParsedIntent(
            IntentType.UNRESOLVED,
            span,
            book=book,
            chapter=numbers.chapter,
            verse_start=numbers.start,
            reasons=(CROSS_CHAPTER,),
        )
    if numbers.start is None:
        intent = IntentType.SELECT_CHAPTER
    elif numbers.start == numbers.end:
        intent = IntentType.SET_REFERENCE
    else:
        intent = IntentType.SET_RANGE
    return ParsedIntent(
        intent,
        span,
        book=book,
        chapter=numbers.chapter,
        verse_start=numbers.start,
        verse_end=numbers.end,
    )


def _correction_word(c: _Cursor) -> bool:
    """Consume one correction phrase. "No" only counts in front of another
    ("no, sorry"), because "John 3:16, no one comes..." is not a correction."""
    for start in (c.i, c.i + 1):
        if start > c.i and not _is_word(c.tokens, c.i, "no"):
            break
        for phrase in _CORRECTIONS:
            window = c.tokens[start : start + len(phrase)]
            if len(window) == len(phrase) and all(
                _is_word(window, k, w) for k, w in enumerate(phrase)
            ):
                c.i = start + len(phrase)
                return True
    return False


def _is_word(tokens: Sequence[Token], i: int, word: str) -> bool:
    return i < len(tokens) and tokens[i].kind is Kind.WORD and tokens[i].text == word


def _skip_breaks(c: _Cursor) -> None:
    while c.kind(Kind.BREAK):
        pass
