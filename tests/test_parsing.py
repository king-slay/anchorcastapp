import json
from pathlib import Path

import pytest
from scripture_parser.canon import BOOKS, Book
from scripture_parser.commands import parse_utterance
from scripture_parser.intents import IntentType
from scripture_parser.parsed import ParsedIntent

FIXTURES = Path(__file__).parent / "fixtures"

CASES = json.loads(Path(FIXTURES / "references.json").read_text(encoding="utf-8"))["cases"]


def describe(p: ParsedIntent) -> str:
    """The fixture's notation: ``SET_RANGE ISA 5:7-9``, ``SELECT_VERSE _ _:8``."""
    text = p.intent.value
    if p.book or p.chapter or p.verse_start:
        where = f"{p.book or '_'} {p.chapter or '_'}"
        if p.verse_start:
            where += f":{p.verse_start}"
            if p.verse_end not in (None, p.verse_start):
                where += f"-{p.verse_end}"
        text += " " + where
    if p.offset:
        text += f" {p.offset:+d}"
    if p.requires_confirmation:
        text += " ?"
    return text


@pytest.mark.parametrize("case", CASES, ids=[c["text"] or "(empty)" for c in CASES])
def test_transcript_fixtures(case: dict[str, object]) -> None:
    text = case["text"]
    assert isinstance(text, str)
    assert [describe(p) for p in parse_utterance(text)] == case["expect"]


def test_span_points_at_the_words_used() -> None:
    text = "Turn with me to the book of Isaiah chapter five verse seven, amen"
    [parsed] = parse_utterance(text)
    assert text[slice(*parsed.span)] == "Isaiah chapter five verse seven"


def test_correction_keeps_what_was_said_first() -> None:
    text = "John three sixteen, sorry, verse seventeen"
    [parsed] = parse_utterance(text)
    assert parsed.corrected_from is not None
    assert (parsed.corrected_from.chapter, parsed.corrected_from.verse_start) == (3, 16)
    assert text[slice(*parsed.span)] == text  # the whole correction is the evidence


def test_second_correction_chains_the_audit_trail() -> None:
    [parsed] = parse_utterance("John 3:16, sorry, 17. No, I mean 18")
    assert parsed.verse_start == 18
    assert parsed.corrected_from is not None and parsed.corrected_from.verse_start == 17
    first = parsed.corrected_from.corrected_from
    assert first is not None and first.verse_start == 16


@pytest.mark.parametrize(
    "text",
    [
        "John 3:16 no one comes to the Father",
        "John 3:16. Sorry, one more thing",
        "John 3:16 and 17 people were there",
    ],
)
def test_a_number_after_a_reference_is_not_always_part_of_it(text: str) -> None:
    [parsed] = parse_utterance(text)
    assert (parsed.verse_start, parsed.corrected_from) == (16, None)


def test_ambiguous_commands_say_why() -> None:
    [back] = parse_utterance("go back")
    [more] = parse_utterance("continue")
    assert back.intent is IntentType.HISTORY_BACK and "FR15" in back.reasons[0]
    assert more.intent is IntentType.NEXT_VERSE and "FR16" in more.reasons[0]


def test_cross_chapter_range_says_why() -> None:
    [parsed] = parse_utterance("John 3:16 to 4:2")
    assert parsed.intent is IntentType.UNRESOLVED
    assert "across chapters" in parsed.reasons[0]


def test_ordinary_word_book_counts_when_capitalized_or_marked() -> None:
    assert parse_utterance("numbers six") == []
    assert [p.book for p in parse_utterance("Numbers six")] == ["NUM"]
    assert [p.book for p in parse_utterance("numbers 6:24")] == ["NUM"]


@pytest.mark.parametrize("book", BOOKS, ids=[b.code for b in BOOKS])
def test_every_book_name_is_heard(book: Book) -> None:
    spoken = book.name.replace("1 ", "First ").replace("2 ", "Second ").replace("3 ", "Third ")
    for text in (f"{book.name} 1:1", f"{spoken} chapter one verse one"):
        [parsed] = parse_utterance(text)
        assert (parsed.book, parsed.chapter, parsed.verse_start) == (book.code, 1, 1), text
