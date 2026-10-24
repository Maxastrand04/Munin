import asyncio
import base64
import hashlib
import re
import shutil
from pathlib import Path

import pytest
from mcp import Client

from munin.core import (
    Fragment,
    KthPlaySource,
    NoSpeechError,
    SourceError,
    Vocabulary,
    download_smallest_video,
    parse_kthplay_url,
    parse_source,
    read_slides,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"

ENTRY_ID = "0_1zk8obn5"
FIXED_URL = f"https://play.kth.se/media/t/{ENTRY_ID}"
SLUG_URL = f"https://play.kth.se/media/Föreläsning+4A+Matriser/{ENTRY_ID}"
SHORT_ENTRY_ID = "0_kcveux4p"
SHORT_DURATION_S = 16.4
SMALLEST_FILE_BYTES = 1_334_087
MISSING_ENTRY_ID = "0_zzzzzzzz"
KTHPLAY_LINK = re.compile(r"https://play\.kth\.se/media/t/\w+\?st=\d+")

LINK_FORMS = [
    f"https://play.kth.se/media/Matriser/{ENTRY_ID}",
    f"http://play.kth.se/media/Matriser/{ENTRY_ID}",
    f"play.kth.se/media/Matriser/{ENTRY_ID}",
    f"https://play.kth.se/media/t/{ENTRY_ID}",
    f"http://play.kth.se/media/t/{ENTRY_ID}",
    f"play.kth.se/media/t/{ENTRY_ID}",
    f"https://play.kth.se/media/{ENTRY_ID}",
    f"http://play.kth.se/media/{ENTRY_ID}",
    f"play.kth.se/media/{ENTRY_ID}",
    f"https://PLAY.KTH.SE/media/t/{ENTRY_ID}",
    f"https://play.kth.se/media/t/{ENTRY_ID}?st=90",
    f"https://play.kth.se/media/Matriser/{ENTRY_ID}#comments",
    f"https://play.kth.se/media/Matriser/{ENTRY_ID}/",
]

NOT_VIDEO_LINKS = [
    "https://play.kth.se/channel/SF1624/123456",
    "https://play.kth.se/playlist/details/0_abcdefgh",
    "https://play.kth.se/search?keyword=matriser",
    "https://play.kth.se/media/Matriser/not-an-id",
    f"https://www.play.kth.se/media/t/{ENTRY_ID}",
    f"https://play.kth.se/media/Linjär/Algebra/{ENTRY_ID}",
]


def two_sentences(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields two sentences."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser."), Fragment(65.7, 68.0, "En matris är en tabell.")]


def no_speech(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that finds no speech."""
    return []


def fake_download(calls: list | None = None, written: list | None = None):
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""

    def download(video, workdir: Path) -> Path:
        if calls is not None:
            calls.append(video)
        file = workdir / "video.mp4"
        shutil.copy(SPEECH, file)
        if written is not None:
            written.append(file)
        return file

    return download


def never_download(video, workdir: Path) -> Path:
    raise AssertionError("the downloader ran on what should be a cache hit or a non-video Source")


def unfetchable(video, workdir: Path) -> Path:
    raise SourceError(video.url, "Access to this entry is restricted")


def transcribe_kthplay(url: str, cache_dir: Path, download=None, **kwargs):
    return transcribe(url, cache_dir=cache_dir, recognize=two_sentences, download=download or fake_download(), **kwargs)


def kthplay_page(cache_dir: Path, output_dir: Path, outline: str = "# Matriser\n- Gauss [0:03]") -> str:
    transcript_id = transcribe_kthplay(SLUG_URL, cache_dir).transcript_id
    page = render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=output_dir).page
    return page.read_text(encoding="utf-8")


# Telling a KTH Play link apart


@pytest.mark.parametrize("url", LINK_FORMS)
def test_kthplay_link_parses_to_its_entry_id(url: str):
    """Every accepted KTH Play link form parses to the video's entry ID."""
    assert parse_kthplay_url(url) == KthPlaySource(ENTRY_ID)


def test_parse_source_returns_kthplay_source_for_kthplay_link():
    """parse_source turns a KTH Play video link into a KTH Play Source, not a Path."""
    assert parse_source(SLUG_URL) == KthPlaySource(ENTRY_ID)


@pytest.mark.parametrize("url", NOT_VIDEO_LINKS)
def test_non_video_kthplay_link_is_not_a_kthplay_source(url: str):
    """A play.kth.se link outside the three video shapes is not a KTH Play Source."""
    assert parse_kthplay_url(url) is None


def test_non_video_kthplay_link_raises_source_error_with_new_reason(cache_dir: Path):
    """A non-video play.kth.se link fails like any unrecognised input, with the reason naming all three Source kinds."""
    with pytest.raises(SourceError, match="not a file, a YouTube URL or a KTH Play video URL"):
        transcribe(NOT_VIDEO_LINKS[0], cache_dir=cache_dir, recognize=two_sentences, download=never_download)


# The KTH Play Source


def test_kthplay_url_is_fixed_lecture_address():
    """A KTH Play Source's url is its fixed lecture address."""
    assert KthPlaySource(ENTRY_ID).url == FIXED_URL


def test_kthplay_timestamp_url_appends_st():
    """A KTH Play Timestamp link is the fixed lecture address plus ?st=<seconds>."""
    assert KthPlaySource(ENTRY_ID).timestamp_url(274) == f"{FIXED_URL}?st=274"


# Transcribing a KTH Play Source


def test_kthplay_miss_is_transcribed_fresh(cache_dir: Path):
    """A KTH Play link seen for the first time is transcribed, not served from the cache."""
    assert transcribe_kthplay(SLUG_URL, cache_dir).cached is False


def test_kthplay_miss_downloads_the_parsed_video(cache_dir: Path):
    """The downloader is asked for the KTH Play video the link points at."""
    calls: list = []
    transcribe_kthplay(SLUG_URL, cache_dir, download=fake_download(calls=calls))
    assert calls == [KthPlaySource(ENTRY_ID)]


def test_kthplay_transcript_id_is_sha256_prefix_of_fixed_address(cache_dir: Path):
    """A KTH Play Transcript's ID is the first 12 hex characters of the SHA-256 of the fixed lecture address."""
    expected = hashlib.sha256(FIXED_URL.encode()).hexdigest()[:12]
    assert transcribe_kthplay(SLUG_URL, cache_dir).transcript_id == expected


def test_kthplay_cache_hit_does_not_download(cache_dir: Path):
    """A second call for the same KTH Play video returns the saved Transcript without downloading."""
    transcribe_kthplay(SLUG_URL, cache_dir)
    assert transcribe_kthplay(SLUG_URL, cache_dir, download=never_download).cached is True


@pytest.mark.parametrize("url", LINK_FORMS)
def test_kthplay_link_forms_share_one_transcript(url: str, cache_dir: Path):
    """Every accepted link form of one video hits the Transcript made from another form."""
    first = transcribe_kthplay(SLUG_URL, cache_dir)
    assert transcribe_kthplay(url, cache_dir, download=never_download).transcript_id == first.transcript_id


def test_kthplay_download_is_deleted(cache_dir: Path):
    """After a KTH Play miss, the video file the downloader wrote no longer exists."""
    written: list = []
    transcribe_kthplay(SLUG_URL, cache_dir, download=fake_download(written=written))
    assert not written[0].exists()


def test_kthplay_vocabulary_run_downloads_again(cache_dir: Path):
    """A boosted call on a cached KTH Play Source downloads the video again."""
    calls: list = []
    transcribe_kthplay(SLUG_URL, cache_dir)
    transcribe_kthplay(SLUG_URL, cache_dir, download=fake_download(calls=calls), vocabulary=Vocabulary(["Gauss"]))
    assert len(calls) == 1


def test_kthplay_vocabulary_run_keeps_transcript_id(cache_dir: Path):
    """A boosted run replaces the saved KTH Play Transcript under the same ID."""
    first = transcribe_kthplay(SLUG_URL, cache_dir)
    boosted = transcribe_kthplay(SLUG_URL, cache_dir, vocabulary=Vocabulary(["Gauss"]))
    assert boosted.transcript_id == first.transcript_id


def test_unfetchable_kthplay_video_raises_source_error_naming_fixed_address(cache_dir: Path):
    """A KTH Play video the downloader can't fetch raises SourceError naming the fixed lecture address."""
    with pytest.raises(SourceError, match=re.escape(FIXED_URL)):
        transcribe_kthplay(SLUG_URL, cache_dir, download=unfetchable)


def test_unfetchable_kthplay_video_is_not_cached(cache_dir: Path):
    """After a failed KTH Play download, the same video is transcribed fresh once it can be fetched."""
    with pytest.raises(SourceError):
        transcribe_kthplay(SLUG_URL, cache_dir, download=unfetchable)
    assert transcribe_kthplay(SLUG_URL, cache_dir).cached is False


def test_silent_kthplay_video_raises_no_speech_error(cache_dir: Path):
    """A KTH Play video with no speech raises NoSpeechError."""
    with pytest.raises(NoSpeechError):
        transcribe(SLUG_URL, cache_dir=cache_dir, recognize=no_speech, download=fake_download())


def test_silent_kthplay_video_is_not_cached(cache_dir: Path):
    """After a KTH Play video yields no speech, the same video is transcribed fresh next time."""
    with pytest.raises(NoSpeechError):
        transcribe(SLUG_URL, cache_dir=cache_dir, recognize=no_speech, download=fake_download())
    assert transcribe_kthplay(SLUG_URL, cache_dir).cached is False


# Rendering a KTH Play Mindmap


def test_kthplay_stamp_becomes_kthplay_timestamp_link(cache_dir: Path, tmp_path: Path):
    """A stamp in a KTH Play Transcript's Outline links to the fixed lecture address at that second."""
    page = kthplay_page(cache_dir, tmp_path / "out")
    assert KTHPLAY_LINK.findall(page) == [f"{FIXED_URL}?st=3"]


def test_kthplay_mindmap_lecture_link_is_fixed_address(cache_dir: Path, tmp_path: Path):
    """The page's lecture link is the fixed lecture address, with no ?st."""
    page = kthplay_page(cache_dir, tmp_path / "out")
    assert f'class="source-link" href="{FIXED_URL}"' in page


def test_kthplay_mindmap_has_no_file_links(cache_dir: Path, tmp_path: Path):
    """A KTH Play Transcript's Mindmap never links to the downloaded video file."""
    assert "file://" not in kthplay_page(cache_dir, tmp_path / "out")


def test_kthplay_slide_shows_in_node_panel(deck: Path, cache_dir: Path, tmp_path: Path):
    """A Slide a node lists on a KTH Play Transcript with a Deck is embedded in the page."""
    transcript_id = transcribe_kthplay(SLUG_URL, cache_dir).transcript_id
    slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
    page = render_mindmap(transcript_id, "# Matriser\n- Gauss [slide 2]", cache_dir=cache_dir, output_dir=tmp_path)
    assert base64.b64encode(slides[1].image).decode() in page.page.read_text(encoding="utf-8")


# The MCP adapter


def test_mcp_transcribe_accepts_kthplay_url(cache_dir: Path):
    """The transcribe tool takes a KTH Play link as `source` and returns its Transcript ID."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, download=fake_download())

    async def run():
        async with Client(server) as client:
            return await client.call_tool("transcribe", {"source": SLUG_URL})

    result = asyncio.run(run())
    assert result.structured_content["transcript_id"] == hashlib.sha256(FIXED_URL.encode()).hexdigest()[:12]


# The real KTH Play downloader


@pytest.mark.network
def test_real_kthplay_download_is_smallest_file_on_offer(tmp_path: Path):
    """The default KTH Play downloader fetches the smallest file on offer, mp4-666 of the short video, not the larger hls-715."""
    file = download_smallest_video(KthPlaySource(SHORT_ENTRY_ID), tmp_path)
    assert file.stat().st_size == SMALLEST_FILE_BYTES


@pytest.mark.network
def test_real_kthplay_download_decodes_to_full_length(cache_dir: Path):
    """The default KTH Play downloader's file decodes to the video's full length."""
    result = transcribe(f"https://play.kth.se/media/t/{SHORT_ENTRY_ID}", cache_dir=cache_dir, recognize=two_sentences)
    assert result.duration_s == pytest.approx(SHORT_DURATION_S, abs=1.5)


@pytest.mark.network
def test_real_kthplay_missing_entry_raises_source_error_naming_fixed_address(cache_dir: Path):
    """The default KTH Play downloader turns an entry KTH Play can't serve into SourceError naming its fixed lecture address."""
    with pytest.raises(SourceError, match=re.escape(f"https://play.kth.se/media/t/{MISSING_ENTRY_ID}")):
        transcribe(f"https://play.kth.se/media/t/{MISSING_ENTRY_ID}", cache_dir=cache_dir, recognize=two_sentences)
