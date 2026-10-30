import base64
import hashlib
from pathlib import Path

import pytest

from munin.core import (
    DeckError,
    Fragment,
    OutlineStructureError,
    Slide,
    UnknownDeckError,
    UnknownTranscriptError,
    Vocabulary,
    read_deck,
    read_slides,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


@pytest.fixture
def transcript_id(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def outline(*slides: int, title: str = "Matriser") -> dict:
    """The main topic `title` with one topic Gauss that lists these Slide numbers."""
    gauss = {"type": "topic", "label": "Gauss", "explanation": "", "stamps": [], "slides": list(slides), "children": []}
    return {"type": "main-topic", "label": title, "explanation": "", "stamps": [], "slides": [], "children": [gauss]}


def render(transcript_id: str, outline: dict, cache_dir: Path, tmp_path: Path):
    return render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")


def page_text(transcript_id: str, outline: dict, cache_dir: Path, tmp_path: Path) -> str:
    return render(transcript_id, outline, cache_dir, tmp_path).page.read_text(encoding="utf-8")


def render_deck(deck_id: str, outline: dict, cache_dir: Path, tmp_path: Path):
    return render_deck_mindmap(deck_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")


def deck_page_text(deck_id: str, outline: dict, cache_dir: Path, tmp_path: Path) -> str:
    return render_deck(deck_id, outline, cache_dir, tmp_path).page.read_text(encoding="utf-8")


def deck_id_of(path: Path) -> str:
    """The first 12 hex characters of the SHA-256 of the resolved PDF path."""
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]


def encoded(slide: Slide) -> str:
    return base64.b64encode(slide.image).decode()


# Reading a Deck


def test_slides_are_numbered_from_one(transcript_id: str, deck: Path, cache_dir: Path):
    """Slides are numbered from 1 in page order."""
    slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
    assert [slide.number for slide in slides] == [1, 2, 3]


def test_each_slide_carries_its_page_text(transcript_id: str, deck: Path, cache_dir: Path):
    """Each Slide carries its page's extracted text."""
    slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
    assert [slide.text.strip() for slide in slides] == ["Matriser", "Gausselimination", "Determinant"]


def test_each_slide_image_is_png(transcript_id: str, deck: Path, cache_dir: Path):
    """Each Slide's image is PNG bytes."""
    slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
    assert [slide.image[:8] for slide in slides] == [PNG_SIGNATURE] * 3


def test_deck_path_has_home_expanded(
    transcript_id: str, cache_dir: Path, tmp_path: Path, write_deck, monkeypatch: pytest.MonkeyPatch
):
    """A Deck path starting with `~` is read from the home folder."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    write_deck(tmp_path / "home" / "matriser.pdf", ["Matriser"])
    assert len(read_slides(transcript_id, "~/matriser.pdf", cache_dir=cache_dir)) == 1


# Failures


@pytest.mark.parametrize(
    "contents, reason",
    [(None, "not a file"), (b"not a pdf at all", "not a readable PDF"), ([], "has no pages")],
    ids=["missing", "unreadable", "zero-pages"],
)
def test_bad_deck_raises_deck_error(
    transcript_id: str, cache_dir: Path, tmp_path: Path, write_deck, contents, reason: str
):
    """A missing, unreadable or zero-page PDF raises `DeckError` with the matching reason."""
    path = tmp_path / "bad.pdf"
    if isinstance(contents, bytes):
        path.write_bytes(contents)
    elif contents is not None:
        write_deck(path, contents)
    with pytest.raises(DeckError) as error:
        read_slides(transcript_id, path, cache_dir=cache_dir)
    assert error.value.reason == reason


def test_deck_error_names_the_path_as_given(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """`DeckError.path` is the Deck path as the caller gave it."""
    given = str(tmp_path / "missing.pdf")
    with pytest.raises(DeckError) as error:
        read_slides(transcript_id, given, cache_dir=cache_dir)
    assert error.value.path == given


def test_deck_error_message_names_the_path_and_reason(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The `DeckError` message reads `Cannot read <path>: <reason>`."""
    given = str(tmp_path / "missing.pdf")
    with pytest.raises(DeckError) as error:
        read_slides(transcript_id, given, cache_dir=cache_dir)
    assert str(error.value) == f"Cannot read {given}: not a file"


def test_unknown_transcript_raises(deck: Path, cache_dir: Path):
    """An unknown Transcript ID raises `UnknownTranscriptError`."""
    with pytest.raises(UnknownTranscriptError):
        read_slides("deadbeef0000", deck, cache_dir=cache_dir)


def test_unknown_transcript_is_checked_before_the_deck(cache_dir: Path, tmp_path: Path):
    """An unknown Transcript ID with a missing Deck raises `UnknownTranscriptError`, not `DeckError`."""
    with pytest.raises(UnknownTranscriptError):
        read_slides("deadbeef0000", tmp_path / "missing.pdf", cache_dir=cache_dir)


# Attaching the Deck


def test_failed_read_attaches_nothing(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """After a failed read on a Transcript with no Deck, a Slide number still fails the render."""
    with pytest.raises(DeckError):
        read_slides(transcript_id, tmp_path / "missing.pdf", cache_dir=cache_dir)
    with pytest.raises(OutlineStructureError):
        render(transcript_id, outline(1), cache_dir, tmp_path)


def test_failed_read_keeps_the_earlier_deck(transcript_id: str, deck: Path, cache_dir: Path, tmp_path: Path):
    """A failed read leaves the Deck attached before, so its Slides still reach the page."""
    slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
    with pytest.raises(DeckError):
        read_slides(transcript_id, tmp_path / "missing.pdf", cache_dir=cache_dir)
    assert encoded(slides[1]) in page_text(transcript_id, outline(2), cache_dir, tmp_path)


def test_reading_a_new_deck_replaces_the_old_one(
    transcript_id: str, deck: Path, cache_dir: Path, tmp_path: Path, write_deck
):
    """After a two-page Deck replaces a three-page one, Slide 3 is past the end and fails the render."""
    read_slides(transcript_id, deck, cache_dir=cache_dir)
    read_slides(transcript_id, write_deck(tmp_path / "short.pdf", ["Ett", "Två"]), cache_dir=cache_dir)
    with pytest.raises(OutlineStructureError):
        render(transcript_id, outline(3), cache_dir, tmp_path)


def test_attached_deck_survives_deleting_the_pdf(transcript_id: str, deck: Path, cache_dir: Path, tmp_path: Path):
    """The page shows a Slide even after the PDF it was read from is deleted."""
    slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
    deck.unlink()
    assert encoded(slides[1]) in page_text(transcript_id, outline(2), cache_dir, tmp_path)


# Reading a Deck on its own


def test_read_deck_numbers_slides_from_one(deck: Path, cache_dir: Path):
    """A Deck read on its own returns its Slides numbered from 1 in page order."""
    assert [slide.number for slide in read_deck(deck, cache_dir=cache_dir).slides] == [1, 2, 3]


def test_read_deck_slides_carry_their_page_text(deck: Path, cache_dir: Path):
    """Each Slide of a Deck read on its own carries its page's text."""
    slides = read_deck(deck, cache_dir=cache_dir).slides
    assert [slide.text.strip() for slide in slides] == ["Matriser", "Gausselimination", "Determinant"]


def test_read_deck_slide_images_are_png(deck: Path, cache_dir: Path):
    """Each Slide of a Deck read on its own carries its page as PNG bytes."""
    slides = read_deck(deck, cache_dir=cache_dir).slides
    assert [slide.image[:8] for slide in slides] == [PNG_SIGNATURE] * 3


def test_read_deck_image_only_page_still_has_an_image(cache_dir: Path, tmp_path: Path, write_deck):
    """A page with no text still comes back as a Slide with a PNG image."""
    path = write_deck(tmp_path / "bilder.pdf", [""])
    assert read_deck(path, cache_dir=cache_dir).slides[0].image[:8] == PNG_SIGNATURE


def test_read_deck_id_comes_from_the_resolved_path(deck: Path, cache_dir: Path):
    """The Deck ID is the first 12 hex characters of the SHA-256 of the resolved PDF path."""
    assert read_deck(deck, cache_dir=cache_dir).deck_id == deck_id_of(deck)


def test_read_deck_expands_home(cache_dir: Path, tmp_path: Path, write_deck, monkeypatch: pytest.MonkeyPatch):
    """A Deck path starting with `~` is read from the home folder."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    write_deck(tmp_path / "home" / "matriser.pdf", ["Matriser"])
    assert len(read_deck("~/matriser.pdf", cache_dir=cache_dir).slides) == 1


def test_read_deck_moved_pdf_gets_a_new_id(deck: Path, cache_dir: Path, tmp_path: Path):
    """The same PDF at a new path is a new Deck with a different ID."""
    first = read_deck(deck, cache_dir=cache_dir).deck_id
    moved = deck.rename(tmp_path / "flyttad.pdf")
    assert read_deck(moved, cache_dir=cache_dir).deck_id != first


def test_read_deck_default_cache_is_where_render_looks(
    deck: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """With no cache_dir, a Deck read on its own renders with no cache_dir too."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    deck_id = read_deck(deck).deck_id
    assert render_deck_mindmap(deck_id, outline(2), output_dir=tmp_path / "out").page.is_file()


@pytest.mark.parametrize(
    "contents, reason",
    [(None, "not a file"), (b"not a pdf at all", "not a readable PDF"), ([], "has no pages")],
    ids=["missing", "unreadable", "zero-pages"],
)
def test_read_deck_bad_deck_raises_deck_error(cache_dir: Path, tmp_path: Path, write_deck, contents, reason: str):
    """A missing, unreadable or zero-page PDF read on its own raises `DeckError` with the matching reason."""
    path = tmp_path / "bad.pdf"
    if isinstance(contents, bytes):
        path.write_bytes(contents)
    elif contents is not None:
        write_deck(path, contents)
    with pytest.raises(DeckError) as error:
        read_deck(path, cache_dir=cache_dir)
    assert error.value.reason == reason


def test_read_deck_failure_stores_nothing(cache_dir: Path, tmp_path: Path):
    """A failed read of a path never read before stores no copy, so rendering its ID raises `UnknownDeckError`."""
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf at all")
    with pytest.raises(DeckError):
        read_deck(path, cache_dir=cache_dir)
    with pytest.raises(UnknownDeckError):
        render_deck(deck_id_of(path), outline(), cache_dir, tmp_path)


def test_read_deck_failure_keeps_the_earlier_copy(deck: Path, cache_dir: Path, tmp_path: Path):
    """A failed re-read of a path leaves the copy stored before, so its Slides still reach the page."""
    first = read_deck(deck, cache_dir=cache_dir)
    deck.write_bytes(b"not a pdf at all")
    with pytest.raises(DeckError):
        read_deck(deck, cache_dir=cache_dir)
    page = deck_page_text(first.deck_id, outline(2), cache_dir, tmp_path)
    assert encoded(first.slides[1]) in page


def test_read_deck_again_replaces_the_copy(deck: Path, cache_dir: Path, tmp_path: Path, write_deck):
    """Re-reading the same path replaces the stored copy, and the next render shows the new Slides."""
    read_deck(deck, cache_dir=cache_dir)
    write_deck(deck, ["Vektorer", "Baser"])
    second = read_deck(deck, cache_dir=cache_dir)
    page = deck_page_text(second.deck_id, outline(2, title="Vektorer"), cache_dir, tmp_path)
    assert encoded(second.slides[1]) in page


def test_read_deck_leaves_an_attached_copy_alone(
    transcript_id: str, deck: Path, cache_dir: Path, tmp_path: Path, write_deck
):
    """Reading a PDF on its own after changing it leaves the copy attached to a Transcript as it was."""
    attached = read_slides(transcript_id, deck, cache_dir=cache_dir)
    write_deck(deck, ["Vektorer", "Baser"])
    read_deck(deck, cache_dir=cache_dir)
    assert encoded(attached[1]) in page_text(transcript_id, outline(2), cache_dir, tmp_path)


def test_read_slides_leaves_a_standalone_copy_alone(
    transcript_id: str, deck: Path, cache_dir: Path, tmp_path: Path, write_deck
):
    """Attaching a PDF to a Transcript after changing it leaves the copy read on its own as it was."""
    standalone = read_deck(deck, cache_dir=cache_dir)
    write_deck(deck, ["Vektorer", "Baser"])
    read_slides(transcript_id, deck, cache_dir=cache_dir)
    page = deck_page_text(standalone.deck_id, outline(2), cache_dir, tmp_path)
    assert encoded(standalone.slides[1]) in page
