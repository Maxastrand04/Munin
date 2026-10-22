"""Turning raw VAD fragments into Segments, with the merge rule from #2."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

_SENTENCE_ENDS = (".", "?", "!")
_MAX_PAUSE_S = 1.5
_MAX_SEGMENT_S = 20.0


@dataclass(frozen=True)
class Fragment:
    """One raw speech span as VAD and Pianissimo return it. Times are seconds from the Source's start."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Segment:
    """One span of speech in a Transcript, after merging. Times are seconds from the Source's start."""

    start: float
    end: float
    text: str


def merge_fragments(fragments: list[Fragment]) -> list[Segment]:
    """Merge time-ordered fragments into Segments.

    Fragments whose text is empty after `strip()` are dropped. The next fragment
    joins the current Segment, separated by one space, when all three hold:

    - the sentence continues: the current text does not end in `.`, `?` or `!`,
      or the next text starts with a lowercase letter,
    - the pause between the current end and the next start is under 1.5 s,
    - the joined Segment would be at most 20 s long.

    A Segment starts at its first fragment's start and ends at its last fragment's
    end. A single fragment longer than 20 s stays whole. Segment text is stripped.
    An empty input, or one with only empty fragments, returns an empty list.
    """
    segments: list[Segment] = []
    for fragment in _stripped_non_empty(fragments):
        if segments and _continues(segments[-1], fragment):
            last = segments[-1]
            segments[-1] = Segment(last.start, fragment.end, f"{last.text} {fragment.text}")
        else:
            segments.append(Segment(fragment.start, fragment.end, fragment.text))
    return segments


def _stripped_non_empty(fragments: Iterable[Fragment]) -> Iterator[Fragment]:
    for fragment in fragments:
        text = fragment.text.strip()
        if text:
            yield Fragment(fragment.start, fragment.end, text)


def _continues(segment: Segment, fragment: Fragment) -> bool:
    sentence_continues = not segment.text.endswith(_SENTENCE_ENDS) or fragment.text[0].islower()
    return (
        sentence_continues
        and fragment.start - segment.end < _MAX_PAUSE_S
        and fragment.end - segment.start <= _MAX_SEGMENT_S
    )
