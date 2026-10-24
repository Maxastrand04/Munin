"""Reading a Deck's Slides and attaching the Deck to a Transcript."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from munin.core import pdf
from munin.core.cache_paths import default_cache_dir
from munin.core.errors import DeckError
from munin.core.transcribe import cached_entry


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
    given = str(deck)
    cache_dir = cache_dir or default_cache_dir()
    cached_entry(transcript_id, cache_dir=cache_dir)
    path = Path(deck).expanduser().resolve()
    if not path.is_file():
        raise DeckError(given, "not a file")
    try:
        pages = pdf.read_pages(path)
    except ValueError as error:
        raise DeckError(given, "not a readable PDF") from error
    if not pages:
        raise DeckError(given, "has no pages")
    target = deck_path(transcript_id, cache_dir)
    partial = target.with_suffix(".pdf.part")
    shutil.copyfile(path, partial)
    partial.replace(target)
    return tuple(Slide(number, text, image) for number, (text, image) in enumerate(pages, start=1))


def deck_path(transcript_id: str, cache_dir: Path) -> Path:
    """Return where the Deck of a Transcript is kept, whether or not one is attached."""
    return cache_dir / f"{transcript_id}.deck.pdf"
