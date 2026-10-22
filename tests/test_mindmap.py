import re
import shutil
from pathlib import Path

import pytest

from klang_notes.core import Fragment, UnknownTranscriptError, render_mindmap, transcribe

REPO_ROOT = Path(__file__).resolve().parents[1]
TIMESTAMP_LINK = re.compile(r"file://[^\"'\\\s]*#t=\d+")


def one_sentence(wav: Path):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def transcript_of(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def links_in(page: Path) -> list[str]:
    return TIMESTAMP_LINK.findall(page.read_text(encoding="utf-8"))


# Stamps become Timestamp links


def test_stamp_becomes_timestamp_link_to_source(source: Path, cache_dir: Path, tmp_path: Path):
    """An `[m:ss]` stamp becomes a `file://<path>#t=<s>` link to the Transcript's Source."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_mindmap(
        transcript_id, "# Matriser\n- Gauss [4:34]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == [f"{source.resolve().as_uri()}#t=274"]


def test_stamp_counts_minutes_past_an_hour(source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp past 59 minutes resolves to the full seconds offset, so `[75:03]` is 4503 s."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_mindmap(
        transcript_id, "# Matriser\n- Slutet [75:03]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == [f"{source.resolve().as_uri()}#t=4503"]


def test_each_stamped_node_links_to_its_second(source: Path, cache_dir: Path, tmp_path: Path):
    """Every stamped node in the written page carries its own link, at its own stamp's second."""
    transcript_id = transcript_of(source, cache_dir)
    outline = "# Matriser [0:05]\n- Storlek [1:10]\n  - Rader [1:42]\n- Indexering [3:00]"
    page = render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    seconds = [link.rsplit("#t=", 1)[1] for link in links_in(page)]
    assert seconds == ["5", "70", "102", "180"]


def test_unstamped_node_renders_as_plain_label(source: Path, cache_dir: Path, tmp_path: Path):
    """A node with no stamp keeps its label and gets no link."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_mindmap(
        transcript_id, "# Matriser\n- Determinanten", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    text = page.read_text(encoding="utf-8")
    assert "Determinanten" in text
    assert links_in(page) == []


def test_link_to_source_with_spaces_and_swedish_letters_is_percent_encoded(
    tmp_path: Path, source: Path, cache_dir: Path
):
    """A Source path with spaces and å, ä, ö links through its percent-encoded `file://` URI."""
    odd = tmp_path / "Föreläsning å ä ö" / "linjär algebra.m4a"
    odd.parent.mkdir()
    shutil.copy(source, odd)
    transcript_id = transcript_of(odd, cache_dir)
    page = render_mindmap(
        transcript_id, "# Matriser\n- Gauss [4:34]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    [link] = links_in(page)
    assert link == f"{odd.resolve().as_uri()}#t=274"
    assert " " not in link and "ö" not in link


# Writing the page


def test_render_writes_page_named_after_transcript_id(source: Path, cache_dir: Path, tmp_path: Path):
    """The page lands in the output folder as `<transcript_id>.html` and its absolute path comes back."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    page = render_mindmap(transcript_id, "# Matriser", cache_dir=cache_dir, output_dir=output_dir)
    assert page == output_dir / f"{transcript_id}.html"
    assert page.is_absolute() and page.is_file()


def test_render_again_overwrites_page(source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering the same Transcript ID again replaces the page with the new Outline."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    render_mindmap(transcript_id, "# Första versionen", cache_dir=cache_dir, output_dir=output_dir)
    page = render_mindmap(transcript_id, "# Andra versionen", cache_dir=cache_dir, output_dir=output_dir)
    text = page.read_text(encoding="utf-8")
    assert "Andra versionen" in text
    assert "Första versionen" not in text


def test_default_output_folder_ignores_working_directory(
    source: Path, cache_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Without an output folder, pages land in the same repo folder whatever the working directory."""
    transcript_id = transcript_of(source, cache_dir)
    pages = []
    for cwd in (tmp_path, REPO_ROOT / "src"):
        monkeypatch.chdir(cwd)
        pages.append(render_mindmap(transcript_id, "# Matriser", cache_dir=cache_dir))
    pages[0].unlink()
    assert pages[0] == pages[1]
    assert pages[0].parent.parent == REPO_ROOT


# Failures


def test_unknown_transcript_id_raises(cache_dir: Path):
    """An ID with no cached Transcript raises UnknownTranscriptError."""
    with pytest.raises(UnknownTranscriptError, match="deadbeef0000"):
        render_mindmap("deadbeef0000", "# Matriser", cache_dir=cache_dir)


def test_unknown_transcript_id_writes_nothing(cache_dir: Path, tmp_path: Path):
    """An unknown ID leaves the output folder untouched."""
    output_dir = tmp_path / "out"
    with pytest.raises(UnknownTranscriptError):
        render_mindmap("deadbeef0000", "# Matriser", cache_dir=cache_dir, output_dir=output_dir)
    assert not output_dir.exists()
