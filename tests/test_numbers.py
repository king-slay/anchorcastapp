import pytest
from scripture_parser.numbers import read_number
from scripture_parser.tokens import Kind, tokenize


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("seven", (7, 1)),
        ("sixteen", (16, 1)),
        ("twenty", (20, 1)),
        ("twenty three", (23, 2)),
        ("one hundred", (100, 2)),
        ("a hundred and fifty", (150, 4)),
        ("one hundred and nineteen", (119, 4)),
        ("hundred five", (105, 2)),
        ("one hundred and", (100, 2)),  # a trailing "and" is not part of it
        ("three sixteen", (3, 1)),  # chapter then verse, not 316
        ("twenty one five", (21, 2)),
    ],
)
def test_spoken_numbers(words: str, expected: tuple[int, int]) -> None:
    assert read_number(words.split()) == expected


@pytest.mark.parametrize("words", ["first", "a", "and", "verse", "zero", ""])
def test_not_numbers(words: str) -> None:
    assert read_number(words.split()) is None


def test_tokens_keep_their_place_in_the_text() -> None:
    text = "Psalm one hundred and nineteen, uh, verse 105"
    tokens = tokenize(text)
    assert [(t.kind, t.text) for t in tokens] == [
        (Kind.WORD, "psalm"),
        (Kind.NUM, "119"),
        (Kind.WORD, "verse"),
        (Kind.NUM, "105"),
    ]
    assert text[tokens[1].start : tokens[1].end] == "one hundred and nineteen"
    assert not tokens[1].digits and tokens[3].digits


def test_written_forms() -> None:
    assert [t.kind for t in tokenize("Jn 3.16-18")] == [
        Kind.WORD,
        Kind.NUM,
        Kind.COLON,
        Kind.NUM,
        Kind.DASH,
        Kind.NUM,
    ]
    assert [t.text for t in tokenize("twenty-three, Let\u2019s")] == ["23", "let's"]
    assert [t.kind for t in tokenize("Amen. Next!")] == [
        Kind.WORD,
        Kind.BREAK,
        Kind.WORD,
        Kind.BREAK,
    ]
