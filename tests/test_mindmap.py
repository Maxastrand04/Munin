import base64
import re
import shutil
from pathlib import Path

import pytest

from munin.core import (
    Fragment,
    OutlineStructureError,
    Slide,
    UnknownDeckError,
    UnknownTranscriptError,
    Video,
    Vocabulary,
    read_deck,
    read_slides,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
TIMESTAMP_LINK = re.compile(r"file://[^\"'\\\s]*#t=\d+")
YOUTUBE_LINK = re.compile(r"https://www\.youtube\.com/watch\?v=[\w-]{11}&t=\d+s")
VIDEO_ID = "dQw4w9WgXcQ"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
KTHPLAY_LINK = re.compile(r"https://play\.kth\.se/media/t/\w+\?st=\d+")
ENTRY_ID = "0_1zk8obn5"
FIXED_URL = f"https://play.kth.se/media/t/{ENTRY_ID}"
SLUG_URL = f"https://play.kth.se/media/Föreläsning+4A+Matriser/{ENTRY_ID}"


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def transcript_of(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def fake_download(video: Video, workdir: Path) -> Path:
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""
    audio = workdir / "audio.m4a"
    shutil.copy(SPEECH, audio)
    return audio


def video_transcript_of(url: str, cache_dir: Path) -> str:
    return transcribe(url, cache_dir=cache_dir, recognize=one_sentence, download=fake_download).transcript_id


def node(kind: str, label: str, *children: dict, stamps=(), slides=(), explanation: str = "") -> dict:
    """A node of a type with children, with every part present."""
    return {
        "type": kind,
        "label": label,
        "explanation": explanation,
        "stamps": list(stamps),
        "slides": list(slides),
        "children": list(children),
    }


def term(label: str = "Gauss", **parts) -> dict:
    return node("term", label, **parts)


def lecture(*terms: dict) -> dict:
    """The main topic Matriser, one topic Rader, one slide node Slide 1, and these nodes under it."""
    return node("main-topic", "Matriser", node("topic", "Rader", node("slide", "Slide 1", *terms)))


def render_page(*args, **kwargs) -> Path:
    """Render a Mindmap and return only its page's path."""
    return render_mindmap(*args, **kwargs).page


def links_in(page: Path) -> list[str]:
    return TIMESTAMP_LINK.findall(page.read_text(encoding="utf-8"))


def encoded(slide: Slide) -> str:
    return base64.b64encode(slide.image).decode()


# Stamps become Timestamp links


def test_stamp_becomes_timestamp_link_to_source(source: Path, cache_dir: Path, tmp_path: Path):
    """An `m:ss` stamp becomes a `file://<path>#t=<s>` link to the Transcript's Source."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert links_in(page) == [f"{source.resolve().as_uri()}#t=3"]


def test_each_stamped_node_links_to_its_second(source: Path, cache_dir: Path, tmp_path: Path):
    """Every stamped node in the written page carries its own link, at its own stamp's second."""
    transcript_id = transcript_of(source, cache_dir)
    outline = node(
        "main-topic",
        "Matriser",
        node("topic", "Storlek", node("slide", "Rader", term("Indexering", stamps=["0:04"]), stamps=["0:03"]), stamps=["0:02"]),
        stamps=["0:01"],
    )
    page = render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    seconds = [link.rsplit("#t=", 1)[1] for link in links_in(page)]
    assert seconds == ["1", "2", "3", "4"]


def test_unstamped_node_keeps_its_label(source: Path, cache_dir: Path, tmp_path: Path):
    """A node with no stamp keeps its label."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(transcript_id, lecture(term("Determinanten")), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert "Determinanten" in page.read_text(encoding="utf-8")


def test_unstamped_node_gets_no_link(source: Path, cache_dir: Path, tmp_path: Path):
    """A node with no stamp gets no link."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(transcript_id, lecture(term("Determinanten")), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert links_in(page) == []


def test_link_to_source_with_spaces_and_swedish_letters_is_percent_encoded(
    tmp_path: Path, source: Path, cache_dir: Path
):
    """A Source path with spaces and å, ä, ö links through its percent-encoded `file://` URI."""
    odd = tmp_path / "Föreläsning å ä ö" / "linjär algebra.m4a"
    odd.parent.mkdir()
    shutil.copy(source, odd)
    transcript_id = transcript_of(odd, cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert links_in(page) == [f"{odd.resolve().as_uri()}#t=3"]


def test_youtube_stamp_becomes_youtube_timestamp_link(cache_dir: Path, tmp_path: Path):
    """A stamp in a YouTube Transcript's Outline links to the video at that second."""
    transcript_id = video_transcript_of(f"https://youtu.be/{VIDEO_ID}", cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert YOUTUBE_LINK.findall(page.read_text(encoding="utf-8")) == [f"{WATCH_URL}&t=3s"]


def test_youtube_mindmap_has_no_file_links(cache_dir: Path, tmp_path: Path):
    """A YouTube Transcript's Mindmap never links to the downloaded audio file."""
    transcript_id = video_transcript_of(WATCH_URL, cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert "file://" not in page.read_text(encoding="utf-8")


def test_kthplay_stamp_becomes_kthplay_timestamp_link(cache_dir: Path, tmp_path: Path):
    """A stamp in a KTH Play Transcript's Outline links to the fixed lecture address at that second."""
    transcript_id = video_transcript_of(SLUG_URL, cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert KTHPLAY_LINK.findall(page.read_text(encoding="utf-8")) == [f"{FIXED_URL}?st=3"]


def test_kthplay_mindmap_has_no_file_links(cache_dir: Path, tmp_path: Path):
    """A KTH Play Transcript's Mindmap never links to the downloaded video file."""
    transcript_id = video_transcript_of(SLUG_URL, cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert "file://" not in page.read_text(encoding="utf-8")


# The page's lecture link


def test_lecture_link_is_source_file_uri(source: Path, cache_dir: Path, tmp_path: Path):
    """A local Source's page links the lecture as its `file://` URI."""
    page = render_page(transcript_of(source, cache_dir), lecture(), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert f'class="source-link" href="{source.resolve().as_uri()}"' in page.read_text(encoding="utf-8")


def test_youtube_lecture_link_is_watch_url(cache_dir: Path, tmp_path: Path):
    """A YouTube Source's page links the lecture as its canonical watch URL, with no `&t`."""
    transcript_id = video_transcript_of(f"https://youtu.be/{VIDEO_ID}", cache_dir)
    page = render_page(transcript_id, lecture(), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert f'class="source-link" href="{WATCH_URL}"' in page.read_text(encoding="utf-8")


def test_kthplay_lecture_link_is_fixed_address(cache_dir: Path, tmp_path: Path):
    """A KTH Play Source's page links the lecture as its fixed lecture address, with no ?st."""
    transcript_id = video_transcript_of(SLUG_URL, cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert f'class="source-link" href="{FIXED_URL}"' in page.read_text(encoding="utf-8")


def test_hour_stamp_becomes_timestamp_link(source: Path, cache_dir: Path, tmp_path: Path):
    """An `h:mm:ss` stamp becomes a Timestamp link at its second."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:00:03"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert links_in(page) == [f"{source.resolve().as_uri()}#t=3"]


def test_stamp_at_source_end_links(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp exactly at the Source's duration becomes a Timestamp link."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:05"])), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert links_in(page) == [f"{five_second_source.resolve().as_uri()}#t=5"]


def test_stamp_in_an_explanation_is_not_checked(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A malformed stamp written in a node's explanation is prose, so the page still renders."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    outline = lecture(term(explanation="Se slutet [1:75]."))
    assert render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out").is_file()


def test_corrected_outline_links_fixed_stamp(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering again with a failing stamp fixed writes the page with that stamp's link."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    output_dir = tmp_path / "out"
    with pytest.raises(OutlineStructureError):
        render_page(transcript_id, lecture(term(stamps=["1:75"])), cache_dir=cache_dir, output_dir=output_dir)
    page = render_page(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir, output_dir=output_dir)
    assert links_in(page) == [f"{five_second_source.resolve().as_uri()}#t=3"]


# Slide numbers link Slides


@pytest.fixture
def slides_transcript(source: Path, deck: Path, cache_dir: Path) -> tuple[str, tuple[Slide, ...]]:
    """A Transcript with the three-page Deck attached, and that Deck's Slides."""
    transcript_id = transcript_of(source, cache_dir)
    return transcript_id, read_slides(transcript_id, deck, cache_dir=cache_dir)


def test_unlisted_slide_is_not_embedded(slides_transcript, cache_dir: Path, tmp_path: Path):
    """The page embeds no image of a Slide that no node lists."""
    transcript_id, slides = slides_transcript
    page = render_page(transcript_id, lecture(term(slides=[2])), cache_dir=cache_dir, output_dir=tmp_path)
    assert encoded(slides[2]) not in page.read_text(encoding="utf-8")


def test_slide_on_two_nodes_is_embedded_once(slides_transcript, cache_dir: Path, tmp_path: Path):
    """A Slide listed on two nodes appears in the page exactly once."""
    transcript_id, slides = slides_transcript
    outline = lecture(term("Gauss", slides=[2]), term("Rang", slides=[2]))
    page = render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path)
    assert page.read_text(encoding="utf-8").count(encoded(slides[1])) == 1


def test_kthplay_slide_image_is_embedded(deck: Path, cache_dir: Path, tmp_path: Path):
    """A Slide a node lists on a KTH Play Transcript with a Deck is embedded in the page."""
    transcript_id = video_transcript_of(SLUG_URL, cache_dir)
    slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
    page = render_page(transcript_id, lecture(term(slides=[2])), cache_dir=cache_dir, output_dir=tmp_path)
    assert encoded(slides[1]) in page.read_text(encoding="utf-8")


def test_slide_number_in_an_explanation_is_not_checked(slides_transcript, cache_dir: Path, tmp_path: Path):
    """A Slide number past the Deck's end written in a node's explanation is prose, so the page still renders."""
    transcript_id, _ = slides_transcript
    outline = lecture(term(slides=[2], explanation="Se även slide 9."))
    assert render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path).is_file()


# Writing the page


def test_render_returns_page_path_named_after_transcript_id(source: Path, cache_dir: Path, tmp_path: Path):
    """The returned path is `<transcript_id>.html` in the output folder."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    page = render_page(transcript_id, lecture(), cache_dir=cache_dir, output_dir=output_dir)
    assert page == output_dir / f"{transcript_id}.html"


def test_render_returns_absolute_path(source: Path, cache_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The returned path is absolute even when the output folder is given relative."""
    transcript_id = transcript_of(source, cache_dir)
    monkeypatch.chdir(tmp_path)
    page = render_page(transcript_id, lecture(), cache_dir=cache_dir, output_dir=Path("out"))
    assert page.is_absolute()


def test_render_writes_page_file(source: Path, cache_dir: Path, tmp_path: Path):
    """The page exists on disk after rendering."""
    transcript_id = transcript_of(source, cache_dir)
    page = render_page(transcript_id, lecture(), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert page.is_file()


def test_render_again_writes_new_outline(source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering the same Transcript ID again puts the new Outline in the page."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    render_page(transcript_id, node("main-topic", "Första versionen"), cache_dir=cache_dir, output_dir=output_dir)
    page = render_page(transcript_id, node("main-topic", "Andra versionen"), cache_dir=cache_dir, output_dir=output_dir)
    assert "Andra versionen" in page.read_text(encoding="utf-8")


def test_render_again_drops_old_outline(source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering the same Transcript ID again leaves nothing of the earlier Outline."""
    transcript_id = transcript_of(source, cache_dir)
    output_dir = tmp_path / "out"
    render_page(transcript_id, node("main-topic", "Första versionen"), cache_dir=cache_dir, output_dir=output_dir)
    page = render_page(transcript_id, node("main-topic", "Andra versionen"), cache_dir=cache_dir, output_dir=output_dir)
    assert "Första versionen" not in page.read_text(encoding="utf-8")


def test_default_output_folder_ignores_working_directory(
    source: Path, cache_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Without an output folder, pages land in the same repo folder whatever the working directory."""
    transcript_id = transcript_of(source, cache_dir)
    pages = []
    for cwd in (tmp_path, REPO_ROOT / "src"):
        monkeypatch.chdir(cwd)
        pages.append(render_page(transcript_id, lecture(), cache_dir=cache_dir))
    pages[0].unlink()
    assert pages[0] == pages[1]


def test_default_output_folder_is_in_the_repo(source: Path, cache_dir: Path):
    """Without an output folder, pages land in a folder at the repo root."""
    page = render_page(transcript_of(source, cache_dir), lecture(), cache_dir=cache_dir)
    page.unlink()
    assert page.parent.parent == REPO_ROOT


# Failures


def test_unknown_transcript_id_raises(cache_dir: Path):
    """An ID with no cached Transcript raises UnknownTranscriptError."""
    with pytest.raises(UnknownTranscriptError, match="deadbeef0000"):
        render_page("deadbeef0000", lecture(), cache_dir=cache_dir)


def test_unknown_transcript_id_writes_nothing(cache_dir: Path, tmp_path: Path):
    """An unknown ID leaves the output folder untouched."""
    output_dir = tmp_path / "out"
    with pytest.raises(UnknownTranscriptError):
        render_page("deadbeef0000", lecture(), cache_dir=cache_dir, output_dir=output_dir)
    assert not output_dir.exists()


# Rendering against a Deck read on its own


@pytest.fixture
def standalone_deck(deck: Path, cache_dir: Path):
    """The three-page Deck read on its own, with no Transcript."""
    return read_deck(deck, cache_dir=cache_dir)


def test_deck_render_writes_page_named_by_deck_id(standalone_deck, cache_dir: Path, tmp_path: Path):
    """The page is `<deck_id>.html` in the output folder."""
    deck_id = standalone_deck.deck_id
    page = render_deck_mindmap(deck_id, lecture(), cache_dir=cache_dir, output_dir=tmp_path / "out").page
    assert page == (tmp_path / "out" / f"{deck_id}.html").resolve()


def test_deck_render_accepts_a_slide_node_with_no_slide_numbers(standalone_deck, cache_dir: Path, tmp_path: Path):
    """A slide node with no Slide numbers renders."""
    outline = lecture(term("Gauss"))
    page = render_deck_mindmap(standalone_deck.deck_id, outline, cache_dir=cache_dir, output_dir=tmp_path).page
    assert page.is_file()


def test_deck_page_has_no_lecture_link(standalone_deck, cache_dir: Path, tmp_path: Path):
    """The page's header carries no link to a Source."""
    outline = lecture(term(slides=[2]))
    page = render_deck_mindmap(standalone_deck.deck_id, outline, cache_dir=cache_dir, output_dir=tmp_path).page
    assert 'class="source-link"' not in page.read_text(encoding="utf-8")


def test_unknown_deck_id_raises(cache_dir: Path, tmp_path: Path):
    """An ID with no Deck read on its own raises `UnknownDeckError`."""
    with pytest.raises(UnknownDeckError):
        render_deck_mindmap("deadbeef0000", lecture(), cache_dir=cache_dir, output_dir=tmp_path)


def test_unknown_deck_error_message_names_the_id(cache_dir: Path, tmp_path: Path):
    """The `UnknownDeckError` message reads `No Deck with ID <id>`."""
    with pytest.raises(UnknownDeckError) as error:
        render_deck_mindmap("deadbeef0000", lecture(), cache_dir=cache_dir, output_dir=tmp_path)
    assert str(error.value) == "No Deck with ID deadbeef0000"


def test_unknown_deck_id_writes_nothing(cache_dir: Path, tmp_path: Path):
    """An unknown Deck ID writes no page."""
    with pytest.raises(UnknownDeckError):
        render_deck_mindmap("deadbeef0000", lecture(), cache_dir=cache_dir, output_dir=tmp_path)
    assert not (tmp_path / "deadbeef0000.html").exists()


def test_deck_render_rejects_id_that_is_not_12_hex(deck: Path, cache_dir: Path, tmp_path: Path):
    """An ID outside the 12-hex form raises `UnknownDeckError`, even if a Deck sits at that name."""
    cache_dir.mkdir()
    shutil.copy(deck, tmp_path / "outside.standalone.pdf")
    with pytest.raises(UnknownDeckError):
        render_deck_mindmap("../outside", lecture(), cache_dir=cache_dir, output_dir=tmp_path / "out")


INJECTED_LABEL = '</script><img src=x onerror=alert(1)> __CSS__ & "lecture"'
INJECTED_EXPLANATION = "</script> __JS__ __TITLE__"


@pytest.fixture
def injected_page(source: Path, cache_dir: Path, tmp_path: Path) -> Path:
    return render_page(
        transcript_of(source, cache_dir),
        node("main-topic", INJECTED_LABEL, explanation=INJECTED_EXPLANATION),
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )


def test_outline_text_cannot_end_script(injected_page: Path):
    assert injected_page.read_text().count("</script>") == 1


def test_outline_text_cannot_inject_html(injected_page: Path):
    assert "<img src=x" not in injected_page.read_text()


def test_outline_text_is_html_escaped_outside_script(injected_page: Path):
    assert "&lt;/script&gt;" in injected_page.read_text()


@pytest.fixture
def fresh_page(source: Path, cache_dir: Path, tmp_path: Path) -> Path:
    return render_page(
        transcript_of(source, cache_dir),
        node("main-topic", "En annan föreläsning", node("topic", "Första idén", stamps=["0:03"])),
        cache_dir=cache_dir,
        output_dir=tmp_path,
    )


def test_new_page_uses_outline_title(fresh_page: Path):
    assert "<title>En annan föreläsning · Munin</title>" in fresh_page.read_text()


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
