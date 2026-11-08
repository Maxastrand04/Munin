import base64
import json
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from munin.core import (
    Fragment,
    OutlineStructureError,
    OutlineSyntaxError,
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
SAMPLE_OUTLINES = ["matriser-outline.json", "gauss-sats-outline.json"]
SLIDE_PATH = ("Matriser", "Rader", "Slide 1")
WORKED_PATH = (*SLIDE_PATH, "Rad gånger kolonn")
WORKED_TYPES = ["example", "exercise"]
BROKEN_LATEX = "$\\frac{1}{2$"
TEN_MINUTES_S = 600
SAMPLE_RATE = 8_000


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def english_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one English sentence."""
    return [Fragment(1.2, 3.0, "Today we talk about matrices.")]


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


def term(label: str = "Gauss", *children: dict, **parts) -> dict:
    return node("term", label, *children, **parts)


def worked(
    kind: str,
    label: str,
    *,
    task: str = "Lös x + 1 = 2",
    steps=(("x = 2 - 1", "subtrahera 1"),),
    answer: str = "x = 1",
) -> dict:
    """An example or exercise node, with every part present."""
    return {
        "type": kind,
        "label": label,
        "stamps": [],
        "slides": [],
        "task": task,
        "steps": [{"calculation": calculation, "reason": reason} for calculation, reason in steps],
        "answer": answer,
    }


def lecture(*under_slide: dict, slides=()) -> dict:
    """The main topic Matriser, one topic Rader, one slide node Slide 1 listing `slides`, and these nodes under it."""
    return node("main-topic", "Matriser", node("topic", "Rader", node("slide", "Slide 1", *under_slide, slides=slides)))


def render_page(*args, **kwargs) -> Path:
    """Render a Mindmap and return only its page's path."""
    return render_mindmap(*args, **kwargs).page


def links_in(page: Path) -> list[str]:
    return TIMESTAMP_LINK.findall(page.read_text(encoding="utf-8"))


def encoded(slide: Slide) -> str:
    return base64.b64encode(slide.image).decode()


def problem_paths(transcript_id: str, outline, cache_dir: Path, tmp_path: Path) -> list[tuple[str, ...]]:
    """Render an Outline that must fail the check, and return each problem's path in the order reported."""
    with pytest.raises(OutlineStructureError) as caught:
        render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    return [problem.path for problem in caught.value.problems]


def problem_messages(transcript_id: str, outline, cache_dir: Path, tmp_path: Path) -> list[str]:
    """Render an Outline that must fail the check, and return each problem's message in the order reported."""
    with pytest.raises(OutlineStructureError) as caught:
        render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    return [problem.message for problem in caught.value.problems]


def problems_of(transcript_id: str, outline, cache_dir: Path, tmp_path: Path) -> list[tuple[tuple[str, ...], str]]:
    """Render an Outline that must fail the check, and return each problem as (path, message) in the order reported."""
    with pytest.raises(OutlineStructureError) as caught:
        render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    return [(problem.path, problem.message) for problem in caught.value.problems]


@pytest.fixture
def transcript_id(source: Path, cache_dir: Path) -> str:
    """A Transcript with no Deck."""
    return transcript_of(source, cache_dir)


@pytest.fixture
def english_transcript_id(source: Path, cache_dir: Path) -> str:
    """An English Transcript with no Deck."""
    return transcribe(source, language="en", cache_dir=cache_dir, recognize=english_sentence).transcript_id


@pytest.fixture
def five_second_transcript_id(five_second_source: Path, cache_dir: Path) -> str:
    """A Transcript whose Source lasts exactly 5 seconds, with no Deck."""
    return transcript_of(five_second_source, cache_dir)


@pytest.fixture
def ten_minute_source(tmp_path: Path) -> Path:
    """A WAV of 10 minutes of silence, long enough for every stamp in the sample Outlines."""
    path = tmp_path / "media" / "ten_minutes.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(bytes(2 * TEN_MINUTES_S * SAMPLE_RATE))
    return path


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


def test_slide_number_embeds_its_slide(slides_transcript, cache_dir: Path, tmp_path: Path):
    """A Slide number on a node embeds that Slide's image in the page."""
    transcript_id, slides = slides_transcript
    page = render_page(transcript_id, lecture(term(slides=[2])), cache_dir=cache_dir, output_dir=tmp_path)
    assert encoded(slides[1]) in page.read_text(encoding="utf-8")


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


# Reading the Outline


def test_outline_as_json_text_renders_a_page(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """An Outline passed as JSON text renders a page."""
    outline = json.dumps(lecture(term()), ensure_ascii=False)
    assert render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path).is_file()


def test_slide_node_without_slide_numbers_renders_without_a_deck(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """In a Transcript with no Deck, a slide node with no Slide numbers stands for a part of the lecture and renders."""
    assert render_page(transcript_id, lecture(term()), cache_dir=cache_dir, output_dir=tmp_path).is_file()


@pytest.mark.parametrize("kind", WORKED_TYPES)
@pytest.mark.parametrize("parent", ["main-topic", "topic", "slide", "term"])
def test_example_or_exercise_renders_under_every_other_type(
    transcript_id: str, cache_dir: Path, tmp_path: Path, parent: str, kind: str
):
    """An example or exercise may sit under a main-topic, topic, slide or term node."""
    child = worked(kind, "Rad gånger kolonn")
    outline = {
        "main-topic": node("main-topic", "Matriser", child),
        "topic": node("main-topic", "Matriser", node("topic", "Rader", child)),
        "slide": lecture(child),
        "term": lecture(term("Gauss", child)),
    }[parent]
    assert render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path).is_file()


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_example_or_exercise_with_no_steps_and_no_answer_renders(
    transcript_id: str, cache_dir: Path, tmp_path: Path, kind: str
):
    """An example's or exercise's steps and answer may be empty."""
    outline = lecture(worked(kind, "Rad gånger kolonn", steps=(), answer=""))
    assert render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path).is_file()


def test_newline_in_an_explanation_renders(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """An explanation may hold newlines, since it carries prose and no LaTeX."""
    outline = lecture(term(explanation="Första raden.\nAndra raden."))
    assert render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path).is_file()


@pytest.mark.parametrize("name", SAMPLE_OUTLINES)
def test_repo_sample_outline_renders(ten_minute_source: Path, cache_dir: Path, tmp_path: Path, name: str):
    """Each sample Outline in `docs/examples/` renders against a 10-minute Source."""
    outline = (REPO_ROOT / "docs" / "examples" / name).read_text(encoding="utf-8")
    transcript_id = transcript_of(ten_minute_source, cache_dir)
    assert render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out").is_file()


def test_text_that_is_not_json_raises_syntax_error(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """Outline text that is not JSON raises `OutlineSyntaxError`."""
    with pytest.raises(OutlineSyntaxError):
        render_page(transcript_id, '{"type": "main-topic",', cache_dir=cache_dir, output_dir=tmp_path)


def test_markdown_outline_raises_syntax_error(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A Markdown Outline is not JSON, so it raises `OutlineSyntaxError`."""
    with pytest.raises(OutlineSyntaxError):
        render_page(transcript_id, "# Matriser\n## Rader [0:01]\n", cache_dir=cache_dir, output_dir=tmp_path)


def test_syntax_error_gives_line_and_column(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The error gives the line and column where parsing broke, both counted from 1."""
    with pytest.raises(OutlineSyntaxError) as caught:
        render_page(transcript_id, '{\n  "type": "main-topic",\n  "label": }', cache_dir=cache_dir, output_dir=tmp_path)
    assert (caught.value.line, caught.value.column) == (3, 12)


def test_syntax_error_message_names_the_position(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The error's message names the line and column where parsing broke."""
    with pytest.raises(OutlineSyntaxError) as caught:
        render_page(transcript_id, '{\n  "type": "main-topic",\n  "label": }', cache_dir=cache_dir, output_dir=tmp_path)
    assert "line 3, column 12" in str(caught.value)


def test_syntax_error_message_points_at_the_schema_tool(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The error's message tells the LLM to call `get_outline_schema`."""
    with pytest.raises(OutlineSyntaxError) as caught:
        render_page(transcript_id, "# Matriser\n", cache_dir=cache_dir, output_dir=tmp_path)
    assert "get_outline_schema" in str(caught.value)


def test_text_that_is_not_json_writes_nothing(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A render that fails on text that is not JSON writes no page."""
    with pytest.raises(OutlineSyntaxError):
        render_page(transcript_id, "# Matriser\n", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


# The Outline check: shape and nesting


def test_unknown_type_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A node of an unknown type fails the check, named by its label path."""
    outline = lecture(node("definition", "Gauss"))
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


@pytest.mark.parametrize("kind", ["exempel", "övning"])
def test_swedish_type_name_is_an_unknown_type(transcript_id: str, cache_dir: Path, tmp_path: Path, kind: str):
    """A node typed `exempel` or `övning` is one unknown-type problem, named by its label path."""
    outline = lecture(worked(kind, "Rad gånger kolonn"))
    assert problems_of(transcript_id, outline, cache_dir, tmp_path) == [(WORKED_PATH, f'unknown type "{kind}"')]


def test_node_with_no_type_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A node with no `type` fails the check, named by its label path."""
    outline = lecture({key: value for key, value in term().items() if key != "type"})
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


def test_child_that_is_not_an_object_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A child that is not an object fails the check, named by its position among its siblings."""
    outline = lecture(term(), "Pivot")
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "#2")]


def test_step_missing_its_reason_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A step with no `reason` fails the check, even though a reason may be empty."""
    example = worked("example", "Rad gånger kolonn")
    example["steps"] = [{"calculation": "x = 2 - 1"}]
    assert problem_paths(transcript_id, lecture(example), cache_dir, tmp_path) == [(*SLIDE_PATH, "Rad gånger kolonn")]


def test_step_with_a_part_it_does_not_have_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A step with a key other than `calculation` and `reason` fails the check, naming the step and the key."""
    example = worked("example", "Rad gånger kolonn")
    example["steps"] = [{"calculation": "x = 2 - 1", "reason": "", "note": "kort"}]
    assert problem_messages(transcript_id, lecture(example), cache_dir, tmp_path) == ['step 1 has no "note" part']


def test_part_of_the_wrong_kind_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A part of the wrong kind, such as stamps given as one string, fails the check."""
    outline = lecture({**term(), "stamps": "0:01"})
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


@pytest.mark.parametrize("slide", ["2", 2.5, True], ids=["text", "fraction", "boolean"])
def test_slide_number_that_is_not_an_integer_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path, slide):
    """A Slide number that is not an integer is a part of the wrong kind."""
    outline = lecture(term(slides=[slide]))
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


def test_missing_part_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A node missing one of its type's parts, even one that may be empty, fails the check."""
    outline = lecture({key: value for key, value in term().items() if key != "explanation"})
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_example_or_exercise_missing_its_task_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path, kind: str):
    """An example or exercise must carry a task."""
    child = {key: value for key, value in worked(kind, "Rad gånger kolonn").items() if key != "task"}
    assert problems_of(transcript_id, lecture(child), cache_dir, tmp_path) == [(WORKED_PATH, "missing task")]


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_part_the_type_does_not_have_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path, kind: str):
    """An example or exercise with an explanation fails the check, since those nodes have no explanation."""
    outline = lecture({**worked(kind, "Rad gånger kolonn"), "explanation": ""})
    assert problems_of(transcript_id, outline, cache_dir, tmp_path) == [(WORKED_PATH, f'{kind} nodes have no "explanation" part')]


def test_misspelled_part_is_a_problem_of_its_own(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A term whose explanation key is misspelled fails for the unknown key and for the missing explanation."""
    parts = {key: value for key, value in term().items() if key != "explanation"}
    outline = lecture({**parts, "explenation": "En metod."})
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss"), (*SLIDE_PATH, "Gauss")]


@pytest.mark.parametrize("kind", WORKED_TYPES)
@pytest.mark.parametrize(
    "children",
    [[], [worked("example", "Inre")], [worked("exercise", "Inre")], [term("Inre")]],
    ids=["empty", "example", "exercise", "term"],
)
def test_children_on_an_example_or_exercise_is_one_problem(
    transcript_id: str, cache_dir: Path, tmp_path: Path, kind: str, children: list
):
    """An example or exercise with a `children` part fails once, whatever the list holds, so nothing nests under one."""
    outline = lecture({**worked(kind, "Rad gånger kolonn"), "children": children})
    assert problems_of(transcript_id, outline, cache_dir, tmp_path) == [(WORKED_PATH, f'{kind} nodes have no "children" part')]


def labelled_node(kind: str, label: str) -> tuple[dict, tuple[str, ...]]:
    """An Outline holding a node of this type with this label, and that node's label path."""
    return {
        "main-topic": (node("main-topic", label), (label,)),
        "topic": (node("main-topic", "Matriser", node("topic", label)), ("Matriser", label)),
        "slide": (node("main-topic", "Matriser", node("topic", "Rader", node("slide", label))), ("Matriser", "Rader", label)),
        "term": (lecture(term(label)), (*SLIDE_PATH, label)),
        "example": (lecture(worked("example", label)), (*SLIDE_PATH, label)),
        "exercise": (lecture(worked("exercise", label)), (*SLIDE_PATH, label)),
    }[kind]


@pytest.mark.parametrize("kind", ["main-topic", "topic", "slide", "term", *WORKED_TYPES])
@pytest.mark.parametrize(
    "label, prefix",
    [
        ("Exempel: Gauss", "Exempel:"),
        ("EXEMPEL: Gauss", "Exempel:"),
        ("exempel : Gauss", "Exempel:"),
        ("  Exempel : Gauss", "Exempel:"),
        ("Övning: Gauss", "Övning:"),
        ("ÖVNING: Gauss", "Övning:"),
        ("övning : Gauss", "Övning:"),
    ],
)
def test_label_with_a_worked_prefix_is_a_problem(
    transcript_id: str, cache_dir: Path, tmp_path: Path, kind: str, label: str, prefix: str
):
    """A label starting with `Exempel:` or `Övning:`, in any case, fails on any node, and says to use a worked node."""
    outline, path = labelled_node(kind, label)
    message = f'label starts with "{prefix}"; use an example or exercise node and leave the prefix out, since the page adds it'
    assert problems_of(transcript_id, outline, cache_dir, tmp_path) == [(path, message)]


@pytest.mark.parametrize("label", ["Exempel på rader", "Övningar", "Ett exempel: rader"])
def test_label_mentioning_an_example_without_the_prefix_renders(
    transcript_id: str, cache_dir: Path, tmp_path: Path, label: str
):
    """Only the `Exempel:` and `Övning:` prefixes fail, so a label that names an example some other way renders."""
    assert render_page(transcript_id, lecture(term(label)), cache_dir=cache_dir, output_dir=tmp_path / "out").exists()


@pytest.mark.parametrize("kind", WORKED_TYPES)
@pytest.mark.parametrize("label", ["Example: Gauss", "Exercise: Gauss"])
def test_english_prefix_on_an_example_or_exercise_renders(
    transcript_id: str, cache_dir: Path, tmp_path: Path, kind: str, label: str
):
    """Only the Swedish prefixes fail, so an example or exercise labelled `Example:` or `Exercise:` renders."""
    outline = lecture(worked(kind, label))
    assert render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out").exists()


@pytest.mark.parametrize(
    "label",
    ["Example: Rows", "EXAMPLE: Rows", "example : Rows", "  Example : Rows", "Exercise: Rows", "EXERCISE: Rows", "exercise : Rows"],
)
def test_english_prefix_fails_an_english_render(english_transcript_id: str, cache_dir: Path, tmp_path: Path, label: str):
    """On an English Transcript, a label starting with `Example:` or `Exercise:`, in any case, fails the render."""
    assert problem_messages(english_transcript_id, lecture(term(label)), cache_dir, tmp_path)


@pytest.mark.parametrize("label, prefix", [("example : Rows", "Example:"), ("EXERCISE: Rows", "Exercise:")])
def test_english_prefix_problem_names_the_prefix_capitalized(
    english_transcript_id: str, cache_dir: Path, tmp_path: Path, label: str, prefix: str
):
    """The problem for a banned English prefix names it capitalized."""
    [message] = problem_messages(english_transcript_id, lecture(term(label)), cache_dir, tmp_path)
    assert f'"{prefix}"' in message


@pytest.mark.parametrize("label", ["Exempel: Rader", "Övning: Rader"])
def test_swedish_prefix_renders_on_an_english_transcript(
    english_transcript_id: str, cache_dir: Path, tmp_path: Path, label: str
):
    """Only the English prefixes fail on an English Transcript, so a label starting with `Exempel:` or `Övning:` renders."""
    assert render_page(english_transcript_id, lecture(term(label)), cache_dir=cache_dir, output_dir=tmp_path / "out").exists()


@pytest.mark.parametrize("label", ["Example: Rows", "Exercise: Rows"])
def test_english_prefix_renders_on_a_swedish_transcript(transcript_id: str, cache_dir: Path, tmp_path: Path, label: str):
    """Only the Swedish prefixes fail on a Swedish Transcript, so a label starting with `Example:` or `Exercise:` renders."""
    assert render_page(transcript_id, lecture(term(label)), cache_dir=cache_dir, output_dir=tmp_path / "out").exists()


def test_transcript_cached_without_a_language_bans_the_swedish_prefix(
    legacy_transcript_id: str, cache_dir: Path, tmp_path: Path
):
    """A Transcript cached with no language is Swedish, so a label starting with `Exempel:` fails the render."""
    assert problem_messages(legacy_transcript_id, lecture(term("Exempel: Rader")), cache_dir, tmp_path)


def test_blank_label_is_a_problem_named_by_position(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A node with a blank label fails the check, and its path names it by its position among its siblings."""
    outline = lecture(term("Gauss"), term("   "))
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "#2")]


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_blank_task_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path, kind: str):
    """An example or exercise with a blank task fails the check."""
    outline = lecture(worked(kind, "Rad gånger kolonn", task=" "))
    assert problems_of(transcript_id, outline, cache_dir, tmp_path) == [(WORKED_PATH, "task is blank")]


def test_blank_calculation_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """An exercise with a step whose calculation is blank fails the check."""
    outline = lecture(worked("exercise", "Rad gånger kolonn", steps=(("", "subtrahera 1"),)))
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Rad gånger kolonn")]


@pytest.mark.parametrize(
    "outline, path",
    [
        (node("main-topic", "Matriser", node("topic", "Rader", term())), ("Matriser", "Rader", "Gauss")),
        (node("main-topic", "Matriser", node("slide", "Slide 1")), ("Matriser", "Slide 1")),
        (lecture(node("topic", "Kolonner")), (*SLIDE_PATH, "Kolonner")),
        (lecture(term("Gauss", term("Pivot"))), (*SLIDE_PATH, "Gauss", "Pivot")),
        (node("main-topic", "Matriser", node("main-topic", "Vektorer")), ("Matriser", "Vektorer")),
    ],
    ids=["term-under-topic", "slide-under-main-topic", "topic-under-slide", "term-under-term", "nested-main-topic"],
)
def test_node_under_the_wrong_parent_type_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path, outline, path):
    """A node under a parent type the nesting rules do not allow fails the check."""
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [path]


def test_root_of_another_type_is_a_problem_at_the_root(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """An Outline whose root is a topic fails the check with a problem at the root."""
    assert problem_paths(transcript_id, node("topic", "Rader"), cache_dir, tmp_path) == [()]


def test_root_that_is_a_list_is_a_problem_at_the_root(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """An Outline whose root is a list of main topics fails the check with a problem at the root."""
    outline = json.dumps([node("main-topic", "Matriser"), node("main-topic", "Vektorer")])
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [()]


@pytest.mark.parametrize(
    "outline",
    [
        lecture(term("Gauss\x0celimination")),
        lecture(worked("example", "Bråk", task="Förenkla \x0crac{2}{4}")),
        lecture(worked("example", "Bråk", steps=(("2 \times 2", ""),))),
        lecture(worked("example", "Bråk", steps=(("2 + 2", "\x08eta saknas"),))),
        lecture(worked("example", "Bråk", answer="x \neq 0")),
    ],
    ids=["label", "task", "calculation", "reason", "answer"],
)
def test_control_character_outside_an_explanation_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path, outline):
    """A control character, what JSON makes of an unescaped LaTeX backslash, fails the check in any part but an explanation."""
    assert len(problem_paths(transcript_id, outline, cache_dir, tmp_path)) == 1


# The Outline check: stamps and Slide numbers


def test_malformed_stamp_is_a_problem(five_second_transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A malformed stamp fails the check, named by its node's label path."""
    outline = lecture(term(stamps=["1:75"]))
    assert problem_paths(five_second_transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


def test_stamp_past_the_source_end_is_a_problem(five_second_transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A stamp later than the Source's end fails the check."""
    outline = lecture(term(stamps=["0:06"]))
    assert problem_paths(five_second_transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


def test_slide_number_below_one_is_a_problem(slides_transcript, cache_dir: Path, tmp_path: Path):
    """A Slide number of 0 fails the check."""
    outline = lecture(term(slides=[0]))
    assert problem_paths(slides_transcript[0], outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


def test_slide_number_past_the_deck_end_is_a_problem(slides_transcript, cache_dir: Path, tmp_path: Path):
    """A Slide number past the attached Deck's last Slide fails the check."""
    outline = lecture(term(slides=[4]))
    assert problem_paths(slides_transcript[0], outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


def test_slide_number_listed_twice_on_one_node_is_a_problem(slides_transcript, cache_dir: Path, tmp_path: Path):
    """The same Slide number twice on one node fails the check."""
    outline = lecture(term(slides=[2, 2]))
    assert problem_paths(slides_transcript[0], outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Gauss")]


def test_slide_number_without_a_deck_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """Any Slide number fails the check when the Transcript has no Deck."""
    assert problem_paths(transcript_id, lecture(slides=[1]), cache_dir, tmp_path) == [SLIDE_PATH]


# The Outline check: LaTeX

CHECK_AFTER_A_CLOSED_LOOP = """
import asyncio
from munin.core.latex import calculation_problems

async def first_check():
    calculation_problems("x = 1")

asyncio.run(first_check())
print(calculation_problems("\\\\frac{1}{2"))
"""


def test_latex_check_still_runs_after_the_loop_of_its_first_check_closes():
    """The first LaTeX check may run inside an asyncio loop, as under Playwright, and a check after that loop closes still finds broken LaTeX."""
    run = subprocess.run(
        [sys.executable, "-c", CHECK_AFTER_A_CLOSED_LOOP], check=False, capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert "BrokenLatex" in run.stdout


def test_broken_latex_in_an_explanation_is_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """An explanation holding a `$...$` KaTeX cannot draw fails the check."""
    outline = lecture(term(explanation=f"Hälften är {BROKEN_LATEX}."))
    with pytest.raises(OutlineStructureError):
        render_page(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path)


def test_broken_latex_writes_nothing(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A render that fails on broken LaTeX writes no page."""
    with pytest.raises(OutlineStructureError):
        render_page(transcript_id, lecture(term(explanation=BROKEN_LATEX)), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_broken_latex_problem_names_its_node_by_label_path(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A broken-LaTeX problem's path is the labels from the main topic down to its node."""
    outline = lecture(term("Bråk", explanation=BROKEN_LATEX))
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Bråk")]


@pytest.mark.parametrize(
    "outline, part",
    [
        (lecture(term(explanation=BROKEN_LATEX)), "explanation"),
        (lecture(worked("example", "Rad gånger kolonn", task=f"Lös {BROKEN_LATEX}")), "task"),
        (lecture(worked("example", "Rad gånger kolonn", answer=BROKEN_LATEX)), "answer"),
        (lecture(worked("example", "Rad gånger kolonn", steps=(("x = 1", ""), ("\\frac{1}{2", "")))), "step 2 calculation"),
        (
            lecture(worked("example", "Rad gånger kolonn", steps=(("x = 1", ""), ("x = 2", f"dela med {BROKEN_LATEX}")))),
            "step 2 reason",
        ),
    ],
    ids=["explanation", "task", "answer", "step-calculation", "step-reason"],
)
def test_broken_latex_problem_names_its_part(transcript_id: str, cache_dir: Path, tmp_path: Path, outline, part: str):
    """A broken-LaTeX problem's message starts with the part the piece sits in, steps counted from 1."""
    [message] = problem_messages(transcript_id, outline, cache_dir, tmp_path)
    assert message.startswith(part)


def test_broken_latex_problem_quotes_the_piece_with_its_dollars(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The message holds the broken piece exactly as the part has it, dollars included."""
    outline = lecture(worked("example", "Rad gånger kolonn", task=f"Lös {BROKEN_LATEX} nu"))
    [message] = problem_messages(transcript_id, outline, cache_dir, tmp_path)
    assert BROKEN_LATEX in message


def test_broken_latex_problem_gives_katex_reason(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The message ends with KaTeX's own reason, and where in the piece it hit it."""
    [message] = problem_messages(transcript_id, lecture(term(explanation=BROKEN_LATEX)), cache_dir, tmp_path)
    assert message.endswith(": Unexpected end of input in a macro argument, expected '}' at end of input")


def test_broken_latex_problem_gives_the_position_counted_from_one(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """When KaTeX stops inside the piece, the message says where, counting the piece's characters from 1."""
    [message] = problem_messages(transcript_id, lecture(term(explanation="Se $x + \\foo$.")), cache_dir, tmp_path)
    assert message.endswith("Undefined control sequence: \\foo at position 5")


def test_broken_calculation_is_quoted_whole(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A broken calculation is quoted whole, with no dollars added."""
    outline = lecture(worked("example", "Rad gånger kolonn", steps=(("x = \\frac{1}{2", ""),)))
    [message] = problem_messages(transcript_id, outline, cache_dir, tmp_path)
    assert '"x = \\frac{1}{2"' in message


def test_unclosed_dollar_is_broken_to_the_end_of_the_part(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A `$` with no closing `$` is one broken piece, from that `$` to the end of the part."""
    outline = lecture(worked("example", "Rad gånger kolonn", task="Lös $x + 1 nu"))
    [message] = problem_messages(transcript_id, outline, cache_dir, tmp_path)
    assert '"$x + 1 nu"' in message


def test_double_dollar_is_broken(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """`$$` is broken, since math is never display mode."""
    outline = lecture(worked("example", "Rad gånger kolonn", task="Lös $$x^2 = 4$$"))
    assert any('"$$"' in message for message in problem_messages(transcript_id, outline, cache_dir, tmp_path))


def test_unknown_latex_command_is_broken(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A command KaTeX does not know is broken, though its braces balance."""
    messages = problem_messages(transcript_id, lecture(term(explanation="Se $\\foo{x}$.")), cache_dir, tmp_path)
    assert messages[0].startswith("explanation")


def test_dollar_in_a_calculation_is_broken(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A calculation is LaTeX alone, so a `$` in it is broken."""
    outline = lecture(worked("example", "Rad gånger kolonn", steps=(("$x = 1$", ""),)))
    assert problem_messages(transcript_id, outline, cache_dir, tmp_path)[0].startswith("step 1 calculation")


def test_supported_latex_is_not_a_problem(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """Only the broken piece is a problem, while a matrix KaTeX can draw beside it is not."""
    matrix = term("Matris", explanation="$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$")
    outline = lecture(matrix, term("Bråk", explanation=BROKEN_LATEX))
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Bråk")]


def test_escaped_dollar_does_not_open_math(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """`\\$` is a literal dollar sign, so the broken piece starts at the next real `$`."""
    outline = lecture(term(explanation=f"Kostar 5 \\$ och {BROKEN_LATEX}"))
    [message] = problem_messages(transcript_id, outline, cache_dir, tmp_path)
    assert f'"{BROKEN_LATEX}"' in message


def test_escaped_dollar_inside_math_does_not_close_it(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """`\\$` inside math stays math, so the piece runs to the next real `$`."""
    piece = "$5\\$ + \\frac{1}{2$"
    [message] = problem_messages(transcript_id, lecture(term(explanation=f"Pris {piece}")), cache_dir, tmp_path)
    assert f'"{piece}"' in message


def test_latex_in_a_label_is_not_checked(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A label is not checked, so broken LaTeX in one gives no problem."""
    outline = lecture(term(BROKEN_LATEX), term("Bråk", explanation=BROKEN_LATEX))
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Bråk")]


def test_latex_in_a_part_of_the_wrong_kind_is_not_checked(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A part that is not a string gives only its wrong-kind problem, whatever LaTeX it holds."""
    outline = lecture(term(explanation=[BROKEN_LATEX]))
    assert problem_messages(transcript_id, outline, cache_dir, tmp_path) == ["explanation must be a string"]


def test_two_broken_pieces_in_one_part_are_two_problems(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """Each broken piece in a part is a problem of its own."""
    outline = lecture(term(explanation=f"{BROKEN_LATEX} och $\\foo$"))
    assert len(problem_messages(transcript_id, outline, cache_dir, tmp_path)) == 2


# The Outline check: every problem, at once


def bad_lecture() -> dict:
    """An Outline with three bad nodes, each wrong in one way: a missing part, a blank task and a malformed stamp."""
    missing = {key: value for key, value in term("Pivot").items() if key != "slides"}
    return lecture(missing, worked("example", "Rad gånger kolonn", task=""), term("Gauss", stamps=["1:75"]))


BAD_PATHS = [(*SLIDE_PATH, "Pivot"), (*SLIDE_PATH, "Rad gånger kolonn"), (*SLIDE_PATH, "Gauss")]


def test_every_problem_is_listed(five_second_transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The check lists every problem it finds, shape and stamp problems together, not just the first."""
    assert sorted(problem_paths(five_second_transcript_id, bad_lecture(), cache_dir, tmp_path)) == sorted(BAD_PATHS)


def test_problems_follow_outline_order(five_second_transcript_id: str, cache_dir: Path, tmp_path: Path):
    """Problems come in Outline order."""
    assert problem_paths(five_second_transcript_id, bad_lecture(), cache_dir, tmp_path) == BAD_PATHS


def test_structure_error_message_names_each_problem_path(five_second_transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The error's message gives each problem's label path joined by ` › `."""
    with pytest.raises(OutlineStructureError) as caught:
        render_page(five_second_transcript_id, bad_lecture(), cache_dir=cache_dir, output_dir=tmp_path)
    assert all(" › ".join(path) in str(caught.value) for path in BAD_PATHS)


def test_structure_error_message_names_a_root_problem_as_outline(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A problem with the root itself is written as `Outline: <message>`."""
    with pytest.raises(OutlineStructureError) as caught:
        render_page(transcript_id, node("topic", "Rader"), cache_dir=cache_dir, output_dir=tmp_path)
    assert str(caught.value).startswith("Outline: ")


def test_structure_error_message_ends_pointing_at_the_schema_tool(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The error's message ends by telling the LLM to call `get_outline_schema`."""
    with pytest.raises(OutlineStructureError) as caught:
        render_page(transcript_id, lecture(node("definition", "Gauss")), cache_dir=cache_dir, output_dir=tmp_path)
    assert "get_outline_schema" in str(caught.value).splitlines()[-1]


def test_outline_with_problems_writes_nothing(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A render that fails the check writes no page."""
    with pytest.raises(OutlineStructureError):
        render_page(transcript_id, lecture(node("definition", "Gauss")), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_broken_latex_is_listed_with_other_problems(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """Broken LaTeX is listed in the same error as a malformed stamp, not after a second render."""
    outline = lecture(term("Stamp", stamps=["1:75"]), term("Bråk", explanation=BROKEN_LATEX))
    assert problem_paths(transcript_id, outline, cache_dir, tmp_path) == [(*SLIDE_PATH, "Stamp"), (*SLIDE_PATH, "Bråk")]


# Failures


def test_unknown_transcript_id_raises(cache_dir: Path):
    """An ID with no cached Transcript raises UnknownTranscriptError."""
    with pytest.raises(UnknownTranscriptError, match="deadbeef0000"):
        render_page("deadbeef0000", lecture(), cache_dir=cache_dir)


def test_unknown_transcript_is_raised_before_the_outline_is_read(cache_dir: Path, tmp_path: Path):
    """An unknown Transcript ID raises `UnknownTranscriptError` even when the Outline is not JSON."""
    with pytest.raises(UnknownTranscriptError):
        render_page("deadbeef0000", "# Matriser\n", cache_dir=cache_dir, output_dir=tmp_path)


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


def test_deck_render_embeds_a_numbered_slide(standalone_deck, cache_dir: Path, tmp_path: Path):
    """A Slide number in an Outline rendered against a standalone Deck embeds that Slide."""
    outline = lecture(term(slides=[3]))
    page = render_deck_mindmap(standalone_deck.deck_id, outline, cache_dir=cache_dir, output_dir=tmp_path).page
    assert encoded(standalone_deck.slides[2]) in page.read_text(encoding="utf-8")


def test_deck_render_stamp_is_a_problem(standalone_deck, cache_dir: Path, tmp_path: Path):
    """Any stamp in an Outline rendered against a standalone Deck fails the check, since there is no Source."""
    with pytest.raises(OutlineStructureError) as caught:
        render_deck_mindmap(
            standalone_deck.deck_id, lecture(term(stamps=["0:01"])), cache_dir=cache_dir, output_dir=tmp_path
        )
    assert [problem.path for problem in caught.value.problems] == [(*SLIDE_PATH, "Gauss")]


def test_deck_render_slide_past_the_deck_end_is_a_problem(standalone_deck, cache_dir: Path, tmp_path: Path):
    """A Slide number past the standalone Deck's last Slide fails the check."""
    with pytest.raises(OutlineStructureError) as caught:
        render_deck_mindmap(standalone_deck.deck_id, lecture(term(slides=[4])), cache_dir=cache_dir, output_dir=tmp_path)
    assert [problem.path for problem in caught.value.problems] == [(*SLIDE_PATH, "Gauss")]


@pytest.mark.parametrize("kind", ["exempel", "övning"])
def test_deck_render_swedish_type_name_is_an_unknown_type(standalone_deck, cache_dir: Path, tmp_path: Path, kind: str):
    """A node typed `exempel` or `övning` fails a render against a standalone Deck too."""
    with pytest.raises(OutlineStructureError) as caught:
        render_deck_mindmap(
            standalone_deck.deck_id, lecture(worked(kind, "Rad gånger kolonn")), cache_dir=cache_dir, output_dir=tmp_path
        )
    assert [problem.message for problem in caught.value.problems] == [f'unknown type "{kind}"']


def test_deck_render_broken_latex_is_a_problem(standalone_deck, cache_dir: Path, tmp_path: Path):
    """Broken LaTeX in an Outline rendered against a standalone Deck fails the check."""
    outline = lecture(term(explanation=BROKEN_LATEX))
    with pytest.raises(OutlineStructureError):
        render_deck_mindmap(standalone_deck.deck_id, outline, cache_dir=cache_dir, output_dir=tmp_path)


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


def test_unknown_deck_is_raised_before_the_outline_is_read(cache_dir: Path, tmp_path: Path):
    """An unknown Deck ID raises `UnknownDeckError` even when the Outline is not JSON."""
    with pytest.raises(UnknownDeckError):
        render_deck_mindmap("deadbeef0000", "# Matriser\n", cache_dir=cache_dir, output_dir=tmp_path)


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
