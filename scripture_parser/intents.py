"""What an utterance asks for (PRD §12).

The parser and, later, retrieval propose one of these; only the context
coordinator turns a proposal into a change of context or display (§8).
"""

from enum import StrEnum


class IntentType(StrEnum):
    SET_REFERENCE = "SET_REFERENCE"  # one verse: "John three sixteen"
    SELECT_CHAPTER = "SELECT_CHAPTER"  # a chapter, no verse inferred (FR08): "Psalm twenty three"
    SET_RANGE = "SET_RANGE"  # verses in one chapter: "Isaiah five seven to nine"
    NEXT_VERSE = "NEXT_VERSE"
    PREVIOUS_VERSE = "PREVIOUS_VERSE"
    SELECT_VERSE = "SELECT_VERSE"  # a verse of the current chapter: "verse eight"
    RELATIVE_OFFSET = "RELATIVE_OFFSET"  # "go two verses down"
    REPEAT_PASSAGE = "REPEAT_PASSAGE"  # "read that again"
    HISTORY_BACK = "HISTORY_BACK"  # "go back" (FR15): never undo, never previous verse
    # A book on its own: "turn with me to the book of Romans". Never a candidate;
    # the coordinator lets the chapter said next ("chapter eight verse
    # twenty-eight") use it instead of the book in context.
    NAME_BOOK = "NAME_BOOK"
    QUOTE_MATCH = "QUOTE_MATCH"  # P1 retrieval (FR21)
    UNRESOLVED = "UNRESOLVED"
