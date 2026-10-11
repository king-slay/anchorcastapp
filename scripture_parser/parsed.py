"""What the parser read in an utterance, before any database or context check."""

from dataclasses import dataclass

from scripture_parser.intents import IntentType


@dataclass(frozen=True, slots=True)
class ParsedIntent:
    intent: IntentType
    span: tuple[int, int]  # characters of the utterance this came from (evidence, §12)
    book: str | None = None  # USFM code; None means "the book in context"
    chapter: int | None = None  # None means "the chapter in context"
    verse_start: int | None = None
    verse_end: int | None = None
    offset: int | None = None  # RELATIVE_OFFSET only: +2 is two verses on
    requires_confirmation: bool = False  # ambiguous by its words alone (FR15, FR16)
    reasons: tuple[str, ...] = ()  # why it is ambiguous or unresolved, for the operator
    corrected_from: "ParsedIntent | None" = None  # what the speaker said first (FR17)
