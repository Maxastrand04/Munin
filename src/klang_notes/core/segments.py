"""Turning raw VAD fragments into Segments, with the merge rule from #2."""

from dataclasses import dataclass


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
    current: Segment | None = None
    for fragment in fragments:
        text = fragment.text.strip()
        if not text:
            continue
        if current is not None and _continues(current, fragment.start, fragment.end, text):
            current = Segment(current.start, fragment.end, f"{current.text} {text}")
            continue
        if current is not None:
            segments.append(current)
        current = Segment(fragment.start, fragment.end, text)
    if current is not None:
        segments.append(current)
    return segments


_SENTENCE_ENDS = (".", "?", "!")
_MAX_PAUSE_S = 1.5
_MAX_SEGMENT_S = 20.0


def _continues(current: Segment, start: float, end: float, text: str) -> bool:
    sentence_continues = not current.text.endswith(_SENTENCE_ENDS) or text[0].islower()
    return (
        sentence_continues
        and start - current.end < _MAX_PAUSE_S
        and end - current.start <= _MAX_SEGMENT_S
    )
