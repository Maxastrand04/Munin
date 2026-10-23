"""Reading a Deck's Slides and attaching the Deck to a Transcript."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Slide:
    """One page of a Deck.

    `number` counts from 1 in page order. `text` is the page's extracted text,
    empty for a page that is only an image. `image` is the page drawn as PNG
    bytes.
    """

    number: int
    text: str
    image: bytes


def read_slides(
    transcript_id: str,
    deck: str | os.PathLike[str],
    *,
    cache_dir: Path | None = None,
) -> tuple[Slide, ...]:
    """Attach a Deck to a Transcript and return every Slide in page order.

    `deck` is a path to a PDF. It has `~` expanded and is resolved to an
    absolute path, as a local Source path is. The Deck is copied into the
    cache beside the Transcript, so a later `render_mindmap` uses the Deck as
    it was when read, even if the PDF is moved, changed or deleted. A
    Transcript has at most one Deck, so reading a Deck replaces any Deck
    attached before, whether it was the same file or not. Transcribing the
    Source again with a Vocabulary keeps the Deck attached.

    `cache_dir` defaults to the per-user cache folder for Munin.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID,
    checked before the PDF is opened. Raises `DeckError` when `deck` is not a
    file, is not a readable PDF, or has no pages. Either way nothing is
    attached, and any Deck attached before stays attached.
    """
    raise NotImplementedError
