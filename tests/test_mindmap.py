import json
import re
import shutil
from pathlib import Path

import pytest

from klang_notes.core import (
    Fragment,
    OutlineError,
    UnknownTranscriptError,
    YouTubeSource,
    render_mindmap,
    transcribe,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
TIMESTAMP_LINK = re.compile(r"file://[^\"'\\\s]*#t=\d+")
YOUTUBE_LINK = re.compile(r"https://www\.youtube\.com/watch\?v=[\w-]{11}&t=\d+s")
VIDEO_ID = "dQw4w9WgXcQ"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


def one_sentence(wav: Path):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def transcript_of(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def fake_download(video: YouTubeSource, workdir: Path) -> Path:
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""
    audio = workdir / "audio.m4a"
    shutil.copy(SPEECH, audio)
    return audio


def youtube_transcript_of(url: str, cache_dir: Path) -> str:
    return transcribe(url, cache_dir=cache_dir, recognize=one_sentence, download=fake_download).transcript_id


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


def test_unstamped_node_keeps_its_label(source: Path, cache_dir: Path, tmp_path: Path):
    """A node with no stamp keeps its label."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_mindmap(
        transcript_id, "# Matriser\n- Determinanten", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert "Determinanten" in page.read_text(encoding="utf-8")


def test_unstamped_node_gets_no_link(source: Path, cache_dir: Path, tmp_path: Path):
    """A node with no stamp gets no link."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_mindmap(
        transcript_id, "# Matriser\n- Determinanten", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
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
    assert links_in(page) == [f"{odd.resolve().as_uri()}#t=274"]


def test_youtube_stamp_becomes_youtube_timestamp_link(cache_dir: Path, tmp_path: Path):
    """A stamp in a YouTube Transcript's Outline links to the video at that second."""
    transcript_id = youtube_transcript_of(f"https://youtu.be/{VIDEO_ID}", cache_dir)
    page = render_mindmap(transcript_id, "# Matriser\n- Gauss [4:34]", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert YOUTUBE_LINK.findall(page.read_text(encoding="utf-8")) == [f"{WATCH_URL}&t=274s"]


def test_youtube_mindmap_has_no_file_links(cache_dir: Path, tmp_path: Path):
    """A YouTube Transcript's Mindmap never links to the downloaded audio file."""
    transcript_id = youtube_transcript_of(WATCH_URL, cache_dir)
    page = render_mindmap(transcript_id, "# Matriser\n- Gauss [4:34]", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert "file://" not in page.read_text(encoding="utf-8")


def test_youtube_stamp_counts_minutes_past_an_hour(cache_dir: Path, tmp_path: Path):
    """A YouTube stamp past 59 minutes links to the full seconds offset, so `[75:03]` is `t=4503s`."""
    transcript_id = youtube_transcript_of(WATCH_URL, cache_dir)
    page = render_mindmap(transcript_id, "# Matriser\n- Slutet [75:03]", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert YOUTUBE_LINK.findall(page.read_text(encoding="utf-8")) == [f"{WATCH_URL}&t=4503s"]


# Writing the page


def test_render_returns_page_path_named_after_transcript_id(source: Path, cache_dir: Path, tmp_path: Path):
    """The returned path is `<transcript_id>.html` in the output folder."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    page = render_mindmap(transcript_id, "# Matriser", cache_dir=cache_dir, output_dir=output_dir)
    assert page == output_dir / f"{transcript_id}.html"


def test_render_returns_absolute_path(source: Path, cache_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The returned path is absolute even when the output folder is given relative."""
    transcript_id = transcript_of(source, cache_dir)
    monkeypatch.chdir(tmp_path)
    page = render_mindmap(transcript_id, "# Matriser", cache_dir=cache_dir, output_dir=Path("out"))
    assert page.is_absolute()


def test_render_writes_page_file(source: Path, cache_dir: Path, tmp_path: Path):
    """The page exists on disk after rendering."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_mindmap(transcript_id, "# Matriser", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert page.is_file()


def test_render_again_writes_new_outline(source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering the same Transcript ID again puts the new Outline in the page."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    render_mindmap(transcript_id, "# Första versionen", cache_dir=cache_dir, output_dir=output_dir)
    page = render_mindmap(transcript_id, "# Andra versionen", cache_dir=cache_dir, output_dir=output_dir)
    assert "Andra versionen" in page.read_text(encoding="utf-8")


def test_render_again_drops_old_outline(source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering the same Transcript ID again leaves nothing of the earlier Outline."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    render_mindmap(transcript_id, "# Första versionen", cache_dir=cache_dir, output_dir=output_dir)
    page = render_mindmap(transcript_id, "# Andra versionen", cache_dir=cache_dir, output_dir=output_dir)
    assert "Första versionen" not in page.read_text(encoding="utf-8")


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


def test_default_output_folder_is_in_the_repo(source: Path, cache_dir: Path):
    """Without an output folder, pages land in a folder at the repo root."""
    page = render_mindmap(transcript_of(source, cache_dir), "# Matriser", cache_dir=cache_dir)
    page.unlink()
    assert page.parent.parent == REPO_ROOT


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


def embedded_nodes(page: Path) -> list[dict]:
    return json.JSONDecoder().raw_decode(page.read_text().split("const DATA = ", 1)[1])[
        0
    ]


def test_headings_lists_and_explanations_keep_their_hierarchy(
    source: Path, cache_dir: Path, tmp_path: Path
):
    outline = """# Lecture [0:01]

An explanation of the lecture.

## First group [0:12]
- First idea [0:15]
  - Detail [0:20]
    A simple explanation of the detail.
- Second idea
## Second group
### Another idea
"""
    page = render_mindmap(
        transcript_of(source, cache_dir),
        outline,
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )
    nodes = embedded_nodes(page)
    assert [node["parent"] for node in nodes] == [None, 0, 1, 2, 1, 0, 5]
    assert [node["label"] for node in nodes] == [
        "Lecture",
        "First group",
        "First idea",
        "Detail",
        "Second idea",
        "Second group",
        "Another idea",
    ]
    assert nodes[0]["explanation"] == "An explanation of the lecture."
    assert nodes[3]["explanation"] == "A simple explanation of the detail."
    assert nodes[4]["explanation"] == ""
    assert nodes[4]["links"] == []


def test_multiple_top_level_topics_share_a_main_topic(
    source: Path, cache_dir: Path, tmp_path: Path
):
    page = render_mindmap(
        transcript_of(source, cache_dir),
        "- First [0:01]\n- Second [0:02]",
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )
    nodes = embedded_nodes(page)
    assert [node["parent"] for node in nodes] == [None, 0, 0]
    assert [node["id"] for node in nodes] == [0, 1, 2]
    assert [node["label"] for node in nodes[1:]] == ["First", "Second"]


@pytest.mark.parametrize(
    "outline", ["", "Just prose about matrices [1:00]."], ids=["empty", "prose-only"]
)
def test_outline_without_nodes_raises(
    source: Path, cache_dir: Path, tmp_path: Path, outline: str
):
    """An Outline with no headings or list items raises instead of rendering an empty Mindmap."""
    with pytest.raises(OutlineError, match="no headings or list items"):
        render_mindmap(
            transcript_of(source, cache_dir), outline, cache_dir=cache_dir, output_dir=tmp_path
        )


def test_outline_without_nodes_writes_nothing(
    source: Path, cache_dir: Path, tmp_path: Path
):
    transcript_id = transcript_of(source, cache_dir)
    with pytest.raises(OutlineError):
        render_mindmap(transcript_id, "Just prose.", cache_dir=cache_dir, output_dir=tmp_path)
    assert not (tmp_path / f"{transcript_id}.html").exists()


def test_outline_text_cannot_end_script_or_replace_template_tokens(
    source: Path, cache_dir: Path, tmp_path: Path
):
    label = '</script><img src=x onerror=alert(1)> __CSS__ & "lecture"'
    explanation = "</script> __JS__ __TITLE__"
    page = render_mindmap(
        transcript_of(source, cache_dir),
        f"# {label}\n\n{explanation}",
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )
    text = page.read_text()
    assert text.count("</script>") == 1
    assert "<img src=x" not in text
    assert "&lt;/script&gt;" in text
    assert embedded_nodes(page)[0]["label"] == label
    assert embedded_nodes(page)[0]["explanation"] == explanation


def test_new_page_uses_outline_title_and_contains_no_demo_content(
    source: Path, cache_dir: Path, tmp_path: Path
):
    page = render_mindmap(
        transcript_of(source, cache_dir),
        "# En annan föreläsning\n- Första idén [0:05]",
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )
    text = page.read_text()
    assert "<title>En annan föreläsning · Klang notes</title>" in text
    assert "sZipb-R1hfg" not in text
    assert "Matriser" not in text
    assert "https://cdn." not in text
    assert 'src="http' not in text
    assert "Topic circles" in text
    assert "Radial rings" in text
