import asyncio
import hashlib
import re
import shutil
import time
from pathlib import Path

import pytest
from mcp import Client

from klang_notes.core import (
    Fragment,
    SourceError,
    YouTubeSource,
    render_mindmap,
    transcribe,
)
from klang_notes.mcp_server import create_server

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
SPEECH_DURATION_S = 4.30

VIDEO_ID = "dQw4w9WgXcQ"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
YOUTUBE_LINK = re.compile(r"https://www\.youtube\.com/watch\?v=[\w-]{11}&t=\d+s")

ZOO_VIDEO_URL = "https://youtu.be/jNQXAC9IVRw"
ZOO_DURATION_S = 19
MISSING_VIDEO_ID = "zzzzzzzzzz0"
MISSING_VIDEO_URL = f"https://youtu.be/{MISSING_VIDEO_ID}"


def two_sentences(wav: Path):
    """A recognizer that ignores the audio and yields two sentences."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser."), Fragment(65.7, 68.0, "En matris är en tabell.")]


def fake_download(calls: list | None = None, written: list | None = None):
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""

    def download(video: YouTubeSource, workdir: Path) -> Path:
        if calls is not None:
            calls.append(video)
        audio = workdir / "audio.m4a"
        shutil.copy(SPEECH, audio)
        if written is not None:
            written.append(audio)
        return audio

    return download


def never_download(video: YouTubeSource, workdir: Path) -> Path:
    raise AssertionError("the downloader ran on what should be a cache hit or a non-YouTube Source")


def unfetchable(video: YouTubeSource, workdir: Path) -> Path:
    raise SourceError(video.url, "Video unavailable")


def transcribe_url(url: str, cache_dir: Path, download=None):
    return transcribe(url, cache_dir=cache_dir, recognize=two_sentences, download=download or fake_download())


# Behaviour 3: a miss downloads and transcribes like a local file


def test_youtube_url_miss_is_transcribed_fresh(cache_dir: Path):
    """A YouTube URL seen for the first time is transcribed, not served from the cache."""
    assert transcribe_url(WATCH_URL, cache_dir).cached is False


def test_youtube_url_miss_counts_segments_of_downloaded_audio(cache_dir: Path):
    """The downloaded audio goes through the recognizer and merging like a local file."""
    assert transcribe_url(WATCH_URL, cache_dir).segment_count == 2


def test_youtube_url_miss_reports_downloaded_audio_duration(cache_dir: Path):
    """duration_s is the length of the downloaded audio."""
    assert transcribe_url(WATCH_URL, cache_dir).duration_s == pytest.approx(SPEECH_DURATION_S, abs=0.05)


def test_youtube_url_miss_downloads_the_parsed_video(cache_dir: Path):
    """The downloader is asked for the video the URL points at."""
    calls: list = []
    transcribe_url(WATCH_URL, cache_dir, download=fake_download(calls=calls))
    assert calls == [YouTubeSource(VIDEO_ID)]


def test_youtube_transcript_id_is_sha256_prefix_of_canonical_url(cache_dir: Path):
    """A YouTube Transcript's ID is the first 12 hex characters of the SHA-256 of the canonical watch URL."""
    expected = hashlib.sha256(WATCH_URL.encode()).hexdigest()[:12]
    assert transcribe_url(WATCH_URL, cache_dir).transcript_id == expected


# Behaviour 2: a hit returns the cached Transcript without downloading


def test_youtube_cache_hit_does_not_download(cache_dir: Path):
    """A second call for the same video returns without calling the downloader."""
    transcribe_url(WATCH_URL, cache_dir)
    assert transcribe_url(WATCH_URL, cache_dir, download=never_download).cached is True


def test_youtube_cache_hit_returns_same_id(cache_dir: Path):
    """A cache hit returns the ID of the first run."""
    first = transcribe_url(WATCH_URL, cache_dir)
    assert transcribe_url(WATCH_URL, cache_dir, download=never_download).transcript_id == first.transcript_id


def test_youtube_cache_hit_reports_original_stats(cache_dir: Path):
    """A cache hit reports the duration, Segment count and transcription time of the first run."""
    first = transcribe_url(WATCH_URL, cache_dir)
    hit = transcribe_url(WATCH_URL, cache_dir, download=never_download)
    assert (hit.duration_s, hit.segment_count, hit.transcription_s) == (
        first.duration_s,
        first.segment_count,
        first.transcription_s,
    )


# URL forms of one video share one cache entry


@pytest.mark.parametrize(
    "url",
    [
        f"https://youtu.be/{VIDEO_ID}",
        f"youtu.be/{VIDEO_ID}?t=42",
        f"https://youtube.com/watch?v={VIDEO_ID}",
        f"www.youtube.com/watch?v={VIDEO_ID}",
        f"http://www.youtube.com/watch?v={VIDEO_ID}&list=PLabcdefghijklmnop&index=3",
        f"https://www.youtube.com/watch?t=90&v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}&t=1m30s",
    ],
)
def test_youtube_url_form_hits_canonical_entry(url: str, cache_dir: Path):
    """Every accepted URL form of a video hits the cache entry made from its canonical watch URL."""
    first = transcribe_url(WATCH_URL, cache_dir)
    assert transcribe_url(url, cache_dir, download=never_download).transcript_id == first.transcript_id


# Behaviour 4: the Source is the video, and the downloaded audio is deleted


def test_downloaded_audio_is_deleted(cache_dir: Path):
    """After a YouTube miss, the audio file the downloader wrote no longer exists."""
    written: list = []
    transcribe_url(WATCH_URL, cache_dir, download=fake_download(written=written))
    assert not written[0].exists()


def test_youtube_transcription_time_excludes_download(cache_dir: Path):
    """transcription_s measures recognition only, so a slow download does not count."""

    def slow_download(video: YouTubeSource, workdir: Path) -> Path:
        time.sleep(0.5)
        return fake_download()(video, workdir)

    assert transcribe_url(WATCH_URL, cache_dir, download=slow_download).transcription_s < 0.5


# Behaviour 5: the render tool writes YouTube Timestamp links


def test_youtube_stamp_becomes_youtube_timestamp_link(cache_dir: Path, tmp_path: Path):
    """A stamp in a YouTube Transcript's Outline links to the video at that second."""
    transcript_id = transcribe_url(f"https://youtu.be/{VIDEO_ID}", cache_dir).transcript_id
    page = render_mindmap(transcript_id, "# Matriser\n- Gauss [4:34]", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert YOUTUBE_LINK.findall(page.read_text(encoding="utf-8")) == [f"{WATCH_URL}&t=274s"]


def test_youtube_mindmap_has_no_file_links(cache_dir: Path, tmp_path: Path):
    """A YouTube Transcript's Mindmap never links to the downloaded audio file."""
    transcript_id = transcribe_url(WATCH_URL, cache_dir).transcript_id
    page = render_mindmap(transcript_id, "# Matriser\n- Gauss [4:34]", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert "file://" not in page.read_text(encoding="utf-8")


def test_youtube_stamp_counts_minutes_past_an_hour(cache_dir: Path, tmp_path: Path):
    """A YouTube stamp past 59 minutes links to the full seconds offset, so `[75:03]` is `t=4503s`."""
    transcript_id = transcribe_url(WATCH_URL, cache_dir).transcript_id
    page = render_mindmap(transcript_id, "# Matriser\n- Slutet [75:03]", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert YOUTUBE_LINK.findall(page.read_text(encoding="utf-8")) == [f"{WATCH_URL}&t=4503s"]


# A URL yt-dlp can't fetch


def test_unfetchable_video_raises_source_error(cache_dir: Path):
    """A video the downloader can't fetch raises SourceError out of transcribe."""
    with pytest.raises(SourceError, match=re.escape(WATCH_URL)):
        transcribe_url(f"https://youtu.be/{VIDEO_ID}", cache_dir, download=unfetchable)


def test_unfetchable_video_is_not_cached(cache_dir: Path):
    """After a failed download, the same video is transcribed fresh once it can be fetched."""
    with pytest.raises(SourceError):
        transcribe_url(WATCH_URL, cache_dir, download=unfetchable)
    assert transcribe_url(WATCH_URL, cache_dir).cached is False


# Neither a file nor a YouTube URL


def test_neither_file_nor_youtube_url_raises_source_error_saying_so(tmp_path: Path, cache_dir: Path):
    """A string that is neither an existing file nor a YouTube URL raises SourceError saying so."""
    with pytest.raises(SourceError, match="not a file or a YouTube URL"):
        transcribe(str(tmp_path / "nope.m4a"), cache_dir=cache_dir, recognize=two_sentences, download=never_download)


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        "https://www.youtube.com/playlist?list=PLabcdefghijklmnop",
        "https://www.youtube.com/watch?v=tooshort",
        f"https://vimeo.com/watch?v={VIDEO_ID}",
    ],
)
def test_unaccepted_url_raises_source_error_saying_so(url: str, cache_dir: Path):
    """A URL outside the accepted YouTube forms raises the same error as a missing file, without downloading."""
    with pytest.raises(SourceError, match="not a file or a YouTube URL"):
        transcribe(url, cache_dir=cache_dir, recognize=two_sentences, download=never_download)


# Behaviour 1: the LLM calls the transcribe tool with a YouTube URL


def test_mcp_transcribe_accepts_youtube_url(cache_dir: Path):
    """The transcribe tool takes a YouTube URL as `source` and returns its Transcript ID."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, download=fake_download())

    async def run():
        async with Client(server) as client:
            return await client.call_tool("transcribe", {"source": WATCH_URL})

    result = asyncio.run(run())
    assert result.structured_content["transcript_id"] == hashlib.sha256(WATCH_URL.encode()).hexdigest()[:12]


# The real downloader


@pytest.mark.network
def test_real_downloader_fetches_youtube_audio(cache_dir: Path):
    """The default downloader fetches a public video's audio, which then decodes to its full length."""
    result = transcribe(ZOO_VIDEO_URL, cache_dir=cache_dir, recognize=two_sentences)
    assert result.duration_s == pytest.approx(ZOO_DURATION_S, abs=1.5)


@pytest.mark.network
def test_real_downloader_unavailable_video_raises_source_error_naming_url(cache_dir: Path):
    """The default downloader turns a video YouTube can't serve into SourceError naming its canonical URL."""
    with pytest.raises(SourceError, match=re.escape(f"https://www.youtube.com/watch?v={MISSING_VIDEO_ID}")):
        transcribe(MISSING_VIDEO_URL, cache_dir=cache_dir, recognize=two_sentences)
