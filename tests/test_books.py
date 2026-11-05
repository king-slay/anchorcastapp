import pytest
from scripture_parser.typed_books import find_book


@pytest.mark.parametrize(
    ("typed", "code"),
    [
        ("John", "JHN"),
        ("jn", "JHN"),
        ("JHN", "JHN"),
        ("1 John", "1JN"),
        ("1st John", "1JN"),
        ("First John", "1JN"),
        ("I John", "1JN"),
        ("1 Cor", "1CO"),
        ("1Cor.", "1CO"),
        ("II Cor", "2CO"),
        ("Matt", "MAT"),
        ("mt", "MAT"),
        ("Ps", "PSA"),
        ("Psalm", "PSA"),
        ("Song of Songs", "SNG"),
        ("Song", "SNG"),
        ("phil", "PHP"),
        ("Philem", "PHM"),
        ("Revelations", "REV"),
        ("rev", "REV"),
        ("Isaiah", "ISA"),
        ("Jude", "JUD"),
        ("judg", "JDG"),
        ("Ezek", "EZK"),
        ("3 jn", "3JN"),
    ],
)
def test_typed_book_names(typed: str, code: str) -> None:
    book = find_book(typed)
    assert book is not None
    assert book.code == code


@pytest.mark.parametrize("typed", ["", "j", "jo", "1 j", "ez", "ph", "Tobit", "Maccabees"])
def test_ambiguous_or_unknown_names_find_nothing(typed: str) -> None:
    assert find_book(typed) is None
