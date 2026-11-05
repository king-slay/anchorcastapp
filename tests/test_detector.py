"""What the speech server reports for each transcript line. The cases come
from live sessions and a two-hour church recording (2026-07-31 service)."""

import pytest
from scripture_parser.detector import CONTEXT_FOR_S, NAMED_FOR_S, Detector, Reference, Unresolved


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def detector(clock: Clock) -> Detector:
    return Detector(clock=clock)


def labels(detector: Detector, text: str) -> list[str]:
    return [h.label if isinstance(h, Reference) else "?" for h in detector.hear(text)]


def test_spoken_numbers_are_read_not_added(detector: Detector) -> None:
    # AnchorCast's own detector made this John 19:1
    assert labels(detector, "John three sixteen") == ["John 3:16"]


def test_a_verse_after_a_chapter_goes_with_it(detector: Detector) -> None:
    assert labels(detector, "Ephesians chapter 3.") == ["Ephesians 3"]
    assert labels(detector, "Verse 7.") == ["Ephesians 3:7"]


def test_a_chapter_said_with_a_bare_verse_is_used(detector: Detector) -> None:
    # AnchorCast's own detector kept Hebrews 12 and made this Hebrews 12:16
    detector.hear("Hebrews chapter 12.")
    assert labels(detector, "Chapter 3 verse 16.") == ["Hebrews 3:16"]


def test_a_book_said_alone_waits_for_its_chapter(detector: Detector) -> None:
    detector.hear("John 2, verse 5.")
    assert detector.hear("Fiskings.") == []
    assert labels(detector, "Chapter 2 verse 7.") == ["1 Kings 2:7"]


def test_a_verse_after_a_new_book_asks_for_the_chapter(detector: Detector) -> None:
    detector.hear("Second, Chronicles chapter 3.")
    detector.hear("Verse 7.")
    detector.hear("1st Kings.")
    [heard] = detector.hear("Verse 13.")
    assert isinstance(heard, Unresolved) and heard.reason == "heard 1 Kings but no chapter"


def test_a_named_book_expires(detector: Detector, clock: Clock) -> None:
    detector.hear("Romans 8:28")
    detector.hear("Let us go to John.")
    clock.now += NAMED_FOR_S + 1
    assert labels(detector, "Chapter 1 verse 3.") == ["Romans 1:3"]


def test_context_lasts_minutes_then_expires(detector: Detector, clock: Clock) -> None:
    detector.hear("Galatians chapter 3 from verse 10.")
    clock.now += 240
    assert labels(detector, "Verse 11.") == ["Galatians 3:11"]
    clock.now += CONTEXT_FOR_S + 1
    [heard] = detector.hear("Verse 12.")
    assert isinstance(heard, Unresolved)


def test_numbers_run_together_are_split_and_flagged(detector: Detector) -> None:
    [heard] = detector.hear("John 316.")
    assert isinstance(heard, Reference) and heard.label == "John 3:16" and heard.flagged
    # AnchorCast's own detector showed Proverbs 3:2 at 97%; it may as well
    # have been 23 or 31, so it is not guessed
    [proverbs] = detector.hear("Proverbs 32.")
    assert isinstance(proverbs, Unresolved) and "not in the Bible" in proverbs.reason


def test_a_dropped_first_or_second_suggests_both(detector: Detector) -> None:
    heard = detector.hear("Kings, chapter 1, verse 1.")
    assert [h.label for h in heard if isinstance(h, Reference)] == ["1 Kings 1:1", "2 Kings 1:1"]
    assert all(isinstance(h, Reference) and h.flagged for h in heard)


def test_a_reference_among_book_names_is_flagged(detector: Detector) -> None:
    # tiny.en during prayer
    [heard] = detector.hear("Verse 10, Haggai, Nehemiah, John 3.")
    assert isinstance(heard, Reference) and heard.label == "John 3" and heard.flagged


def test_flagged_references_do_not_become_context(detector: Detector) -> None:
    detector.hear("Luke 17")
    detector.hear("John 316.")
    assert labels(detector, "Verse 5.") == ["Luke 17:5"]


def test_said_twice_is_reported_once(detector: Detector) -> None:
    assert labels(detector, "John 1 verse 15. John 1 verse 15.") == ["John 1:15"]


def test_references_that_do_not_exist_are_not_returned(detector: Detector) -> None:
    [heard] = detector.hear("John 3 verse 90")
    assert isinstance(heard, Unresolved) and "not in the Bible" in heard.reason


def test_next_verse_moves_on(detector: Detector) -> None:
    detector.hear("John 3:16")
    assert labels(detector, "next verse") == ["John 3:17"]
    assert labels(detector, "next verse") == ["John 3:18"]


def test_numbers_ending_a_book_and_ordinary_speech(detector: Detector) -> None:
    assert labels(detector, "Number 10 verse 2.") == ["Numbers 10:2"]
    assert detector.hear("the number 7 is perfect") == []
    assert detector.hear("job one is prayer") == []


def test_json_for_the_app(detector: Detector) -> None:
    [heard] = detector.hear("Proverbs chapter 13 verse 22.")
    assert isinstance(heard, Reference)
    assert heard.as_json() == {
        "book": "Proverbs",
        "code": "PRO",
        "chapter": 13,
        "verse": 22,
        "verse_end": 22,
        "ref": "Proverbs 13:22",
        "flagged": False,
        "reasons": [],
        "span": [0, 28],
    }
