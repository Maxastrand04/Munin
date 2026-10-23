import json
import re
import shutil
from pathlib import Path

import pytest

from klang_notes.core import (
    Fragment,
    OutlineError,
    UnknownTranscriptError,
    UnlinkedStamp,
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


def render_page(*args, **kwargs) -> Path:
    """Render a Mindmap and return only its page's path."""
    return render_mindmap(*args, **kwargs).page


def links_in(page: Path) -> list[str]:
    return TIMESTAMP_LINK.findall(page.read_text(encoding="utf-8"))


def embedded_nodes(page: Path) -> list[dict]:
    return json.JSONDecoder().raw_decode(page.read_text().split("const DATA = ", 1)[1])[
        0
    ]


def labels_in(page: Path) -> list[str]:
    return [node["label"] for node in embedded_nodes(page)]


# Stamps become Timestamp links


def test_stamp_becomes_timestamp_link_to_source(source: Path, cache_dir: Path, tmp_path: Path):
    """An `[m:ss]` stamp becomes a `file://<path>#t=<s>` link to the Transcript's Source."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Gauss [0:03]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == [f"{source.resolve().as_uri()}#t=3"]


def test_each_stamped_node_links_to_its_second(source: Path, cache_dir: Path, tmp_path: Path):
    """Every stamped node in the written page carries its own link, at its own stamp's second."""
    transcript_id = transcript_of(source, cache_dir)
    outline = "# Matriser [0:01]\n- Storlek [0:02]\n  - Rader [0:03]\n- Indexering [0:04]"
    page = render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    seconds = [link.rsplit("#t=", 1)[1] for link in links_in(page)]
    assert seconds == ["1", "2", "3", "4"]


def test_unstamped_node_keeps_its_label(source: Path, cache_dir: Path, tmp_path: Path):
    """A node with no stamp keeps its label."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Determinanten", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert "Determinanten" in page.read_text(encoding="utf-8")


def test_unstamped_node_gets_no_link(source: Path, cache_dir: Path, tmp_path: Path):
    """A node with no stamp gets no link."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(
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
    page = render_page(
        transcript_id, "# Matriser\n- Gauss [0:03]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == [f"{odd.resolve().as_uri()}#t=3"]


def test_youtube_stamp_becomes_youtube_timestamp_link(cache_dir: Path, tmp_path: Path):
    """A stamp in a YouTube Transcript's Outline links to the video at that second."""
    transcript_id = youtube_transcript_of(f"https://youtu.be/{VIDEO_ID}", cache_dir)
    page = render_page(transcript_id, "# Matriser\n- Gauss [0:03]", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert YOUTUBE_LINK.findall(page.read_text(encoding="utf-8")) == [f"{WATCH_URL}&t=3s"]


def test_youtube_mindmap_has_no_file_links(cache_dir: Path, tmp_path: Path):
    """A YouTube Transcript's Mindmap never links to the downloaded audio file."""
    transcript_id = youtube_transcript_of(WATCH_URL, cache_dir)
    page = render_page(transcript_id, "# Matriser\n- Gauss [0:03]", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert "file://" not in page.read_text(encoding="utf-8")


def test_hour_stamp_becomes_timestamp_link(source: Path, cache_dir: Path, tmp_path: Path):
    """An `[h:mm:ss]` stamp becomes a Timestamp link at its second."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Gauss [0:00:03]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == [f"{source.resolve().as_uri()}#t=3"]


def test_stamp_at_source_end_links(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp exactly at the Source's duration becomes a Timestamp link."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Slutet [0:05]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == [f"{five_second_source.resolve().as_uri()}#t=5"]


# Bad stamps stay plain text and are reported


def test_stamp_past_source_end_gets_no_link(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp after the Source's duration gets no Timestamp link."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Slutet [0:06]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == []


def test_stamp_past_source_end_is_reported(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp after the Source's duration is reported as past the end, with its Outline label."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    result = render_mindmap(
        transcript_id, "# Matriser\n- Slutet [0:06]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert result.unlinked == (UnlinkedStamp("Slutet [0:06]", "[0:06]", "past_end"),)


def test_past_end_stamp_stays_in_label_as_text(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp after the Source's duration stays in its node's label on the page as plain text."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Slutet [0:06]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert "Slutet [0:06]" in labels_in(page)


def test_malformed_stamp_gets_no_link(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A malformed stamp gets no Timestamp link."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Gauss [1:75]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == []


def test_malformed_stamp_is_reported(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A malformed stamp is reported as malformed, with its Outline label."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    result = render_mindmap(
        transcript_id, "# Matriser\n- Gauss [1:75]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert result.unlinked == (UnlinkedStamp("Gauss [1:75]", "[1:75]", "malformed"),)


def test_bad_stamp_stays_in_label_as_text(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A bad stamp stays in its node's label on the page as plain text."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Gauss [1:75]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert "Gauss [1:75]" in labels_in(page)


def test_good_stamp_beside_bad_one_still_links(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A good stamp in the same label as a bad one still becomes a Timestamp link."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Gauss [0:02] [1:75]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert links_in(page) == [f"{five_second_source.resolve().as_uri()}#t=2"]


@pytest.mark.parametrize("bracket", ["[se nedan]", "[12]"])
def test_bracket_without_colon_is_not_reported(
    five_second_source: Path, cache_dir: Path, tmp_path: Path, bracket: str
):
    """Bracketed text with no colon or with letters is not a stamp, so it is not reported."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    result = render_mindmap(
        transcript_id, f"# Matriser\n- Gauss {bracket}", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert result.unlinked == ()


@pytest.mark.parametrize("bracket", ["[se nedan]", "[12]"])
def test_bracket_without_colon_stays_in_label(
    five_second_source: Path, cache_dir: Path, tmp_path: Path, bracket: str
):
    """Bracketed text that is not a stamp stays in its node's label."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(
        transcript_id, f"# Matriser\n- Gauss {bracket}", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert f"Gauss {bracket}" in labels_in(page)


def test_outline_without_bad_stamps_reports_none(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """An Outline whose stamps all link reports no unlinked stamps."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    result = render_mindmap(
        transcript_id, "# Matriser [0:01]\n- Gauss [0:04]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert result.unlinked == ()


def test_unlinked_stamps_follow_outline_order(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """Unlinked stamps come in Outline order, left to right in a label, one entry per occurrence."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    outline = "# Matriser\n- Gauss [1:75]\n- Slutet [1:75] [0:09]"
    result = render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert result.unlinked == (
        UnlinkedStamp("Gauss [1:75]", "[1:75]", "malformed"),
        UnlinkedStamp("Slutet [1:75] [0:09]", "[1:75]", "malformed"),
        UnlinkedStamp("Slutet [1:75] [0:09]", "[0:09]", "past_end"),
    )


def test_bad_stamp_in_explanation_is_not_reported(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A bad stamp in a node's explanation prose is not reported."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    result = render_mindmap(
        transcript_id, "# Matriser\n\nSe slutet [1:75].", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert result.unlinked == ()


def test_render_with_bad_stamps_writes_page(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """An Outline with bad stamps still writes the page."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(
        transcript_id, "# Matriser\n- Gauss [1:75]\n- Slutet [0:09]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    )
    assert page.is_file()


def test_corrected_outline_reports_none(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering again with the bad stamps fixed reports no unlinked stamps."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    output_dir = tmp_path / "out"
    render_mindmap(transcript_id, "# Matriser\n- Gauss [1:75]", cache_dir=cache_dir, output_dir=output_dir)
    result = render_mindmap(transcript_id, "# Matriser\n- Gauss [0:03]", cache_dir=cache_dir, output_dir=output_dir)
    assert result.unlinked == ()


def test_corrected_outline_links_fixed_stamp(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering again with a fixed stamp overwrites the page with that stamp's link."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    output_dir = tmp_path / "out"
    render_page(transcript_id, "# Matriser\n- Gauss [1:75]", cache_dir=cache_dir, output_dir=output_dir)
    page = render_page(transcript_id, "# Matriser\n- Gauss [0:03]", cache_dir=cache_dir, output_dir=output_dir)
    assert links_in(page) == [f"{five_second_source.resolve().as_uri()}#t=3"]


# Writing the page


def test_render_returns_page_path_named_after_transcript_id(source: Path, cache_dir: Path, tmp_path: Path):
    """The returned path is `<transcript_id>.html` in the output folder."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    page = render_page(transcript_id, "# Matriser", cache_dir=cache_dir, output_dir=output_dir)
    assert page == output_dir / f"{transcript_id}.html"


def test_render_returns_absolute_path(source: Path, cache_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The returned path is absolute even when the output folder is given relative."""
    transcript_id = transcript_of(source, cache_dir)
    monkeypatch.chdir(tmp_path)
    page = render_page(transcript_id, "# Matriser", cache_dir=cache_dir, output_dir=Path("out"))
    assert page.is_absolute()


def test_render_writes_page_file(source: Path, cache_dir: Path, tmp_path: Path):
    """The page exists on disk after rendering."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(transcript_id, "# Matriser", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert page.is_file()


def test_render_again_writes_new_outline(source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering the same Transcript ID again puts the new Outline in the page."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    render_page(transcript_id, "# Första versionen", cache_dir=cache_dir, output_dir=output_dir)
    page = render_page(transcript_id, "# Andra versionen", cache_dir=cache_dir, output_dir=output_dir)
    assert "Andra versionen" in page.read_text(encoding="utf-8")


def test_render_again_drops_old_outline(source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering the same Transcript ID again leaves nothing of the earlier Outline."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    render_page(transcript_id, "# Första versionen", cache_dir=cache_dir, output_dir=output_dir)
    page = render_page(transcript_id, "# Andra versionen", cache_dir=cache_dir, output_dir=output_dir)
    assert "Första versionen" not in page.read_text(encoding="utf-8")


def test_default_output_folder_ignores_working_directory(
    source: Path, cache_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Without an output folder, pages land in the same repo folder whatever the working directory."""
    transcript_id = transcript_of(source, cache_dir)
    pages = []
    for cwd in (tmp_path, REPO_ROOT / "src"):
        monkeypatch.chdir(cwd)
        pages.append(render_page(transcript_id, "# Matriser", cache_dir=cache_dir))
    pages[0].unlink()
    assert pages[0] == pages[1]


def test_default_output_folder_is_in_the_repo(source: Path, cache_dir: Path):
    """Without an output folder, pages land in a folder at the repo root."""
    page = render_page(transcript_of(source, cache_dir), "# Matriser", cache_dir=cache_dir)
    page.unlink()
    assert page.parent.parent == REPO_ROOT


# Failures


def test_unknown_transcript_id_raises(cache_dir: Path):
    """An ID with no cached Transcript raises UnknownTranscriptError."""
    with pytest.raises(UnknownTranscriptError, match="deadbeef0000"):
        render_page("deadbeef0000", "# Matriser", cache_dir=cache_dir)


def test_unknown_transcript_id_writes_nothing(cache_dir: Path, tmp_path: Path):
    """An unknown ID leaves the output folder untouched."""
    output_dir = tmp_path / "out"
    with pytest.raises(UnknownTranscriptError):
        render_page("deadbeef0000", "# Matriser", cache_dir=cache_dir, output_dir=output_dir)
    assert not output_dir.exists()


HIERARCHY = """# Lecture [0:01]

An explanation of the lecture.

## First group [0:02]
- First idea [0:03]
  - Detail [0:04]
    A simple explanation of the detail.
- Second idea
## Second group
### Another idea
"""


@pytest.fixture
def hierarchy_page(source: Path, cache_dir: Path, tmp_path: Path) -> Path:
    return render_page(transcript_of(source, cache_dir), HIERARCHY, cache_dir=cache_dir, output_dir=tmp_path)


def test_headings_and_list_items_nest_under_their_parents(hierarchy_page: Path):
    assert [node["parent"] for node in embedded_nodes(hierarchy_page)] == [None, 0, 1, 2, 1, 0, 5]


def test_headings_and_list_items_become_labels_without_their_stamps(hierarchy_page: Path):
    assert labels_in(hierarchy_page) == [
        "Lecture",
        "First group",
        "First idea",
        "Detail",
        "Second idea",
        "Second group",
        "Another idea",
    ]


def test_prose_after_a_heading_becomes_its_explanation(hierarchy_page: Path):
    assert embedded_nodes(hierarchy_page)[0]["explanation"] == "An explanation of the lecture."


def test_indented_prose_after_a_list_item_becomes_its_explanation(hierarchy_page: Path):
    assert embedded_nodes(hierarchy_page)[3]["explanation"] == "A simple explanation of the detail."


def test_node_without_prose_has_empty_explanation(hierarchy_page: Path):
    assert embedded_nodes(hierarchy_page)[4]["explanation"] == ""


@pytest.fixture
def two_topic_nodes(source: Path, cache_dir: Path, tmp_path: Path) -> list[dict]:
    page = render_page(
        transcript_of(source, cache_dir),
        "- First [0:01]\n- Second [0:02]",
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )
    return embedded_nodes(page)


def test_multiple_top_level_topics_share_a_main_topic(two_topic_nodes: list[dict]):
    assert [node["parent"] for node in two_topic_nodes] == [None, 0, 0]


def test_multiple_top_level_topics_are_numbered_after_the_main_topic(two_topic_nodes: list[dict]):
    assert [node["id"] for node in two_topic_nodes] == [0, 1, 2]


def test_multiple_top_level_topics_keep_their_labels(two_topic_nodes: list[dict]):
    assert [node["label"] for node in two_topic_nodes[1:]] == ["First", "Second"]


@pytest.mark.parametrize(
    "outline", ["", "Just prose about matrices [1:00]."], ids=["empty", "prose-only"]
)
def test_outline_without_nodes_raises(
    source: Path, cache_dir: Path, tmp_path: Path, outline: str
):
    """An Outline with no headings or list items raises instead of rendering an empty Mindmap."""
    with pytest.raises(OutlineError, match="no headings or list items"):
        render_page(
            transcript_of(source, cache_dir), outline, cache_dir=cache_dir, output_dir=tmp_path
        )


def test_outline_without_nodes_writes_nothing(
    source: Path, cache_dir: Path, tmp_path: Path
):
    transcript_id = transcript_of(source, cache_dir)
    with pytest.raises(OutlineError):
        render_page(transcript_id, "Just prose.", cache_dir=cache_dir, output_dir=tmp_path)
    assert not (tmp_path / f"{transcript_id}.html").exists()


INJECTED_LABEL = '</script><img src=x onerror=alert(1)> __CSS__ & "lecture"'
INJECTED_EXPLANATION = "</script> __JS__ __TITLE__"


@pytest.fixture
def injected_page(source: Path, cache_dir: Path, tmp_path: Path) -> Path:
    return render_page(
        transcript_of(source, cache_dir),
        f"# {INJECTED_LABEL}\n\n{INJECTED_EXPLANATION}",
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )


def test_outline_text_cannot_end_script(injected_page: Path):
    assert injected_page.read_text().count("</script>") == 1


def test_outline_text_cannot_inject_html(injected_page: Path):
    assert "<img src=x" not in injected_page.read_text()


def test_outline_text_is_html_escaped_outside_script(injected_page: Path):
    assert "&lt;/script&gt;" in injected_page.read_text()


def test_label_with_template_tokens_reaches_page_as_written(injected_page: Path):
    assert embedded_nodes(injected_page)[0]["label"] == INJECTED_LABEL


def test_explanation_with_template_tokens_reaches_page_as_written(injected_page: Path):
    assert embedded_nodes(injected_page)[0]["explanation"] == INJECTED_EXPLANATION


@pytest.fixture
def fresh_page(source: Path, cache_dir: Path, tmp_path: Path) -> Path:
    return render_page(
        transcript_of(source, cache_dir),
        "# En annan föreläsning\n- Första idén [0:03]",
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )


def test_new_page_uses_outline_title(fresh_page: Path):
    assert "<title>En annan föreläsning · Klang notes</title>" in fresh_page.read_text()


@pytest.mark.parametrize(
    "text",
    ["sZipb-R1hfg", "Matriser", "https://cdn.", 'src="http'],
    ids=["demo-video", "demo-outline", "cdn", "remote-script"],
)
def test_new_page_contains_no_demo_or_remote_content(fresh_page: Path, text: str):
    assert text not in fresh_page.read_text()


@pytest.mark.parametrize("layout", ["Topic circles", "Radial rings"])
def test_new_page_offers_both_layouts(fresh_page: Path, layout: str):
    assert layout in fresh_page.read_text()
