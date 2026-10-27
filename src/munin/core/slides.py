"""Reading a Deck's Slides, attached to a Transcript or on its own."""

import hashlib
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


@dataclass(frozen=True)
class DeckResult:
    """What `read_deck` tells the caller about a Deck read on its own.

    `deck_id` names the stored copy for `render_deck_mindmap`. `slides` is
    every Slide in page order.
    """

    deck_id: str
    slides: tuple[Slide, ...]


def read_deck(
    deck: str | os.PathLike[str],
    *,
    cache_dir: Path | None = None,
) -> DeckResult:
    """Read a Deck on its own, with no Transcript, and return its ID and every Slide in page order.

    `deck` is a path to a PDF. It has `~` expanded and is resolved to an
    absolute path, as a local Source path is. The Deck ID is the first 12 hex
    characters of the SHA-256 of that resolved path, so the same path always
    gives the same ID, and a moved or renamed PDF gets a new one. The Deck is
    copied into the cache under its ID, so a later `render_deck_mindmap` uses
    the Deck as it was when read. Reading the same path again replaces the
    copy, and the next render uses the new Slides.

    A Deck read on its own and the same PDF attached to a Transcript with
    `read_slides` are separate copies, and reading or replacing one leaves the
    other as it was.

    `cache_dir` defaults to the per-user cache folder for Munin.

    Raises `DeckError` when `deck` is not a file, is not a readable PDF, or
    has no pages. Then nothing is stored, and any copy stored before under
    the same ID stays.
    """
    given = str(deck)
    cache_dir = cache_dir or default_cache_dir()
    path = Path(deck).expanduser().resolve()
    if not path.is_file():
        raise DeckError(given, "not a file")
    try:
        pages = pdf.read_pages(path)
    except ValueError as error:
        raise DeckError(given, "not a readable PDF") from error
    if not pages:
        raise DeckError(given, "has no pages")
    deck_id = hashlib.sha256(str(path).encode()).hexdigest()[:12]
    target = standalone_deck_path(deck_id, cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".pdf.part")
    shutil.copyfile(path, partial)
    partial.replace(target)
    slides = tuple(Slide(number, text, image) for number, (text, image) in enumerate(pages, start=1))
    return DeckResult(deck_id, slides)


def standalone_deck_path(deck_id: str, cache_dir: Path) -> Path:
    """Return where a Deck read on its own is kept, whether or not one was read."""
    return cache_dir / f"{deck_id}.standalone.pdf"


def deck_path(transcript_id: str, cache_dir: Path) -> Path:
    """Return where the Deck of a Transcript is kept, whether or not one is attached."""
    return cache_dir / f"{transcript_id}.deck.pdf"
