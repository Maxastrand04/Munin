import pytest

from klang_notes.core import Fragment, Segment, merge_fragments


def test_merge_drops_fragments_with_only_whitespace():
    """A fragment whose text is empty after strip() produces no Segment."""
    segments = merge_fragments([Fragment(0.0, 1.0, "Hej."), Fragment(5.0, 6.0, "   ")])
    assert segments == [Segment(0.0, 1.0, "Hej.")]


def test_merge_joins_fragment_after_text_without_end_punctuation():
    """A fragment joins the previous one, with one space, when the previous text has no end punctuation."""
    segments = merge_fragments([Fragment(0.0, 2.0, "Det första är"), Fragment(2.5, 4.0, "Matrisens storlek.")])
    assert segments == [Segment(0.0, 4.0, "Det första är Matrisens storlek.")]


def test_merge_joins_lowercase_fragment_after_period():
    """A fragment starting lowercase joins the previous one even when that ends in a period."""
    segments = merge_fragments([Fragment(0.0, 2.0, "Då säger man."), Fragment(2.5, 4.0, "att den är kvadratisk.")])
    assert segments == [Segment(0.0, 4.0, "Då säger man. att den är kvadratisk.")]


@pytest.mark.parametrize("end", [".", "?", "!"])
def test_merge_starts_new_segment_after_sentence_end(end: str):
    """An uppercase fragment after `.`, `?` or `!` starts a new Segment."""
    segments = merge_fragments([Fragment(0.0, 2.0, f"Det är bra{end}"), Fragment(2.5, 4.0, "Nästa sak.")])
    assert segments == [Segment(0.0, 2.0, f"Det är bra{end}"), Segment(2.5, 4.0, "Nästa sak.")]


def test_merge_joins_continuing_sentence_after_pause_just_under_limit():
    """A continuing fragment joins across a pause just under 1.5 s."""
    segments = merge_fragments([Fragment(0.0, 2.0, "Det första är"), Fragment(3.49, 5.0, "storleken.")])
    assert len(segments) == 1


def test_merge_splits_continuing_sentence_at_pause_of_1_5_s():
    """A continuing fragment after a pause of 1.5 s or more starts a new Segment."""
    segments = merge_fragments([Fragment(0.0, 2.0, "Det första är"), Fragment(3.5, 5.0, "storleken.")])
    assert len(segments) == 2


def test_merge_joins_when_result_is_exactly_20_s():
    """A continuing fragment joins when the joined Segment is exactly 20 s long."""
    segments = merge_fragments([Fragment(0.0, 10.0, "Det första är"), Fragment(10.5, 20.0, "storleken.")])
    assert segments == [Segment(0.0, 20.0, "Det första är storleken.")]


def test_merge_splits_when_result_would_exceed_20_s():
    """A continuing fragment starts a new Segment when joining would pass 20 s."""
    segments = merge_fragments([Fragment(0.0, 10.0, "Det första är"), Fragment(10.5, 20.5, "storleken.")])
    assert len(segments) == 2


def test_merge_keeps_single_long_fragment_whole():
    """A single fragment over 20 s becomes one Segment with its own times."""
    segments = merge_fragments([Fragment(3.0, 33.0, "En väldigt lång mening utan paus.")])
    assert segments == [Segment(3.0, 33.0, "En väldigt lång mening utan paus.")]


def test_merge_strips_segment_text():
    """Segment text carries no leading or trailing whitespace."""
    segments = merge_fragments([Fragment(0.0, 1.0, "  Hej.  ")])
    assert segments == [Segment(0.0, 1.0, "Hej.")]


def test_merge_of_no_fragments_is_empty():
    """An empty fragment list gives an empty Segment list."""
    assert merge_fragments([]) == []
