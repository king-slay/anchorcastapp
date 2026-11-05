"""Everything an utterance asks for: explicit references and navigation commands.

Commands ("next verse", "verse eight", "go two verses down", "read that
again", "go back") only count when they make up a whole sentence, give or take
words like "okay", "now", "let's" or "please". Inside a longer sentence they
are commentary: "the next verse is often misunderstood" asks for nothing
(FR19). A command without a book is resolved against accepted context later;
the parser never invents a book or chapter (FR18).
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Final

from scripture_parser.intents import IntentType
from scripture_parser.parsed import ParsedIntent
from scripture_parser.references import find_references
from scripture_parser.spoken_books import match_book
from scripture_parser.tokens import Kind, Token, tokenize

HISTORY_BACK_REASON = "'go back' returns to the previous passage only once confirmed (FR15)"
CONTINUE_REASON = "'continue' could mean several things, so it needs confirmation (FR16)"

BOOK_LIST = "heard among a list of book names; the speech model may be guessing"
_LEAD_INS: Final = (
    ("all", "right"),
    ("let", "us"),
    ("we", "will"),
    ("okay",),
    ("ok",),
    ("alright",),
    ("right",),
    ("now",),
    ("so",),
    ("and",),
    ("then",),
    ("please",),
    ("let's",),
    ("lets",),
    ("we'll",),
    ("amen",),
    ("church",),
    ("everyone",),
)
_TAILS: Final = (
    ("with", "me"),
    ("for", "us"),
    ("please",),
    ("now",),
    ("together",),
    ("everyone",),
    ("church",),
)

_GO = (
    r"(?:(?:(?:go|move|skip|jump|turn|come|get)(?: back| on| down| over| ahead)?"
    r"|back|down|on) to |(?:look|looking) at |(?:read|see|notice) )?"
)
_JOIN = r"(?: (?P<join>to|through|thru|till|until|and) (?:verse )?#)?"
_FORWARD = {"down", "forward", "ahead", "on", "further"}

Builder = Callable[[re.Match[str], list[int], tuple[int, int]], list[ParsedIntent]]


def _next(_: re.Match[str], __: list[int], span: tuple[int, int]) -> list[ParsedIntent]:
    return [ParsedIntent(IntentType.NEXT_VERSE, span)]


def _previous(_: re.Match[str], __: list[int], span: tuple[int, int]) -> list[ParsedIntent]:
    return [ParsedIntent(IntentType.PREVIOUS_VERSE, span)]


def _verses(m: re.Match[str], nums: list[int], span: tuple[int, int]) -> list[ParsedIntent]:
    return _verse_intents(None, nums, m["join"], span)


def _chapter(m: re.Match[str], nums: list[int], span: tuple[int, int]) -> list[ParsedIntent]:
    chapter, verses = nums[0], nums[1:]
    if not verses:
        return [ParsedIntent(IntentType.SELECT_CHAPTER, span, chapter=chapter)]
    return _verse_intents(chapter, verses, m["join"], span)


def _relative(m: re.Match[str], nums: list[int], span: tuple[int, int]) -> list[ParsedIntent]:
    if nums[0] == 0:
        return []
    offset = nums[0] if m["dir"] in _FORWARD else -nums[0]
    return [ParsedIntent(IntentType.RELATIVE_OFFSET, span, offset=offset)]


def _repeat(_: re.Match[str], __: list[int], span: tuple[int, int]) -> list[ParsedIntent]:
    return [ParsedIntent(IntentType.REPEAT_PASSAGE, span)]


def _history_back(_: re.Match[str], __: list[int], span: tuple[int, int]) -> list[ParsedIntent]:
    return [
        ParsedIntent(
            IntentType.HISTORY_BACK,
            span,
            requires_confirmation=True,
            reasons=(HISTORY_BACK_REASON,),
        )
    ]


def _continue(_: re.Match[str], __: list[int], span: tuple[int, int]) -> list[ParsedIntent]:
    return [
        ParsedIntent(
            IntentType.NEXT_VERSE, span, requires_confirmation=True, reasons=(CONTINUE_REASON,)
        )
    ]


_COMMANDS: Final[tuple[tuple[re.Pattern[str], Builder], ...]] = tuple(
    (re.compile(pattern), builder)
    for pattern, builder in (
        (_GO + r"(?:the )?next verse", _next),
        (_GO + r"(?:the )?(?:previous|preceding) verse|" + _GO + r"the verse before", _previous),
        (_GO + r"verses? (?:from )?#" + _JOIN, _verses),
        (_GO + r"chapter #(?: (?:and |from )?verses? (?:from )?#" + _JOIN + r")?", _chapter),
        # "11 verse 7." as a sentence of its own: the speaker named the book
        # just before, or a speech model dropped "chapter"
        (_GO + r"# (?:and )?verses? (?:from )?#" + _JOIN, _chapter),
        (
            r"(?:go|move|skip|jump) (?P<dir>down|forward|ahead|on|back|backward|backwards|up)"
            r" # verses?",
            _relative,
        ),
        (
            r"(?:(?:go|move|skip|jump) )?# verses?"
            r" (?P<dir>down|forward|ahead|on|further|back|backward|backwards|up|earlier)",
            _relative,
        ),
        (
            r"(?:(?:read|say|show|go over) (?:that|it|this|those|these|that verse|the verse"
            r"|this verse|those verses|that passage|the passage|this passage)"
            r" (?:again|one more time))|again|one more time",
            _repeat,
        ),
        (r"go back", _history_back),
        (
            r"continue(?: reading)?|keep (?:reading|going)|read on|go on"
            r"|(?:read |go on to |move on to )?the following verse",
            _continue,
        ),
    )
)


def parse_utterance(text: str) -> list[ParsedIntent]:
    """Every reference and command in ``text``, in the order spoken."""
    tokens = tokenize(text)
    references = find_references(tokens)
    used = {i for found in references for i in found.tokens}
    intents = [found.parsed for found in references]
    if _book_names_left(tokens, used) >= 2:
        # "Verse 10, Haggai, Nehemiah, John 3.": during prayer or tongues the
        # speech model reaches for Bible words; a reference among them is a guess.
        intents = [
            replace(p, requires_confirmation=True, reasons=(*p.reasons, BOOK_LIST)) for p in intents
        ]
    for sentence in _sentences(tokens):
        if not used.intersection(sentence):
            intents.extend(_command([tokens[i] for i in sentence]))
    return sorted(intents, key=lambda p: p.span)


def _book_names_left(tokens: Sequence[Token], used: set[int]) -> int:
    """Book names said on their own, outside any reference."""
    count = 0
    i = 0
    while i < len(tokens):
        match = None if i in used else match_book(tokens, i)
        if match is None or match.ordinary_word or match.abbreviation:
            i += 1
            continue
        count += 1
        i = match.end
    return count


def _sentences(tokens: Sequence[Token]) -> list[list[int]]:
    sentences: list[list[int]] = [[]]
    for i, token in enumerate(tokens):
        if token.kind is Kind.BREAK:
            sentences.append([])
        else:
            sentences[-1].append(i)
    return [s for s in sentences if s]


def _command(tokens: list[Token]) -> list[ParsedIntent]:
    words = [t for t in tokens if t.kind is not Kind.COLON]
    words = _strip(words, _LEAD_INS, from_start=True)
    words = _strip(words, _TAILS, from_start=False)
    if not words:
        return []
    core = " ".join(
        "#" if t.kind is Kind.NUM else "to" if t.kind is Kind.DASH else t.text for t in words
    )
    numbers = [t.value for t in words if t.kind is Kind.NUM]
    span = (words[0].start, words[-1].end)
    for pattern, build in _COMMANDS:
        match = pattern.fullmatch(core)
        if match is not None:
            return build(match, numbers, span)
    return []


def _verse_intents(
    chapter: int | None, numbers: list[int], join: str | None, span: tuple[int, int]
) -> list[ParsedIntent]:
    start = numbers[0]
    end = numbers[1] if len(numbers) > 1 else start
    if join == "and" and end != start + 1:
        # "verses three and seven": two separate verses, in order
        return [_verse(chapter, n, n, span) for n in (start, end)]
    return [_verse(chapter, start, end, span)]


def _verse(chapter: int | None, start: int, end: int, span: tuple[int, int]) -> ParsedIntent:
    intent = IntentType.SELECT_VERSE if start == end else IntentType.SET_RANGE
    return ParsedIntent(intent, span, chapter=chapter, verse_start=start, verse_end=end)


def _strip(
    words: list[Token], phrases: tuple[tuple[str, ...], ...], *, from_start: bool
) -> list[Token]:
    stripped = True
    while stripped and words:
        stripped = False
        for phrase in phrases:
            n = len(phrase)
            window = words[:n] if from_start else words[-n:]
            if len(window) == n and all(
                t.kind is Kind.WORD and t.text == w for t, w in zip(window, phrase, strict=True)
            ):
                words = words[n:] if from_start else words[:-n]
                stripped = True
                break
    return words
