import hashlib
import re
import shutil
import time
import wave
from pathlib import Path

import onnx_asr
import pytest

from klang_notes.core import (
    Fragment,
    NoSpeechError,
    SourceError,
    UnknownTranscriptError,
    YouTubeSource,
    get_transcript,
    transcribe,
)

FIXTURES = Path(__file__).parent / "fixtures"
SPEECH = FIXTURES / "sv_short.m4a"
SPEECH_DURATION_S = 4.30
SILENCE = FIXTURES / "silence.m4a"

VIDEO_ID = "dQw4w9WgXcQ"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
ZOO_VIDEO_URL = "https://youtu.be/jNQXAC9IVRw"
ZOO_DURATION_S = 19
MISSING_VIDEO_ID = "zzzzzzzzzz0"
MISSING_VIDEO_URL = f"https://youtu.be/{MISSING_VIDEO_ID}"


def fake(*fragments: Fragment):
    """A recognizer that ignores the audio and yields the given fragments."""

    def recognize(wav: Path):
        return list(fragments)

    return recognize


def never_called(wav: Path):
    raise AssertionError("the recognizer ran on what should be a cache hit")


TWO_SENTENCES = fake(
    Fragment(1.2, 3.0, "Idag ska vi prata om matriser."),
    Fragment(65.7, 68.0, "En matris är en tabell."),
)


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
    return transcribe(url, cache_dir=cache_dir, recognize=TWO_SENTENCES, download=download or fake_download())


# Fresh run


def test_transcribe_counts_merged_segments(source: Path, cache_dir: Path):
    """segment_count is the number of Segments after merging, not raw fragments."""
    recognize = fake(
        Fragment(0.0, 1.0, "Det första är"),
        Fragment(1.2, 2.0, "storleken."),
        Fragment(2.5, 3.0, " "),
        Fragment(3.5, 4.0, "Sen kommer indexering."),
    )
    result = transcribe(source, cache_dir=cache_dir, recognize=recognize)
    assert result.segment_count == 2


def test_transcribe_reports_source_duration(source: Path, cache_dir: Path):
    """duration_s is the Source's audio length in seconds."""
    result = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    assert result.duration_s == pytest.approx(SPEECH_DURATION_S, abs=0.1)


def test_transcribe_reports_measured_transcription_time(source: Path, cache_dir: Path):
    """transcription_s on a fresh run covers the time the recognizer took."""

    def slow_recognize(wav: Path):
        time.sleep(0.05)
        return [Fragment(0.0, 1.0, "Hej.")]

    result = transcribe(source, cache_dir=cache_dir, recognize=slow_recognize)
    assert result.transcription_s >= 0.05


def test_transcribe_fresh_run_is_not_cached(source: Path, cache_dir: Path):
    """A first transcription reports cached=False."""
    result = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    assert result.cached is False


def test_transcript_id_is_sha256_prefix_of_resolved_path(source: Path, cache_dir: Path):
    """The ID is the first 12 hex characters of the SHA-256 of the resolved path."""
    result = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    assert result.transcript_id == hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:12]


def test_recognizer_gets_16_khz_audio(source: Path, cache_dir: Path):
    """The recognizer receives a wav sampled at 16 kHz."""
    rates = []

    def recognize(wav: Path):
        with wave.open(str(wav)) as w:
            rates.append(w.getframerate())
        return [Fragment(0.0, 1.0, "Hej.")]

    transcribe(source, cache_dir=cache_dir, recognize=recognize)
    assert rates == [16000]


def test_recognizer_gets_mono_audio(source: Path, cache_dir: Path):
    """The recognizer receives a wav with one channel."""
    channels = []

    def recognize(wav: Path):
        with wave.open(str(wav)) as w:
            channels.append(w.getnchannels())
        return [Fragment(0.0, 1.0, "Hej.")]

    transcribe(source, cache_dir=cache_dir, recognize=recognize)
    assert channels == [1]


# Cache hits


def test_cache_hit_does_not_run_recognizer(source: Path, cache_dir: Path):
    """A second call for the same Source never calls the recognizer."""
    transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    transcribe(source, cache_dir=cache_dir, recognize=never_called)


def test_cache_hit_does_not_load_model(source: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """A cache hit with the default recognizer never loads Pianissimo."""

    def no_loading(*args, **kwargs):
        raise AssertionError("the model loaded on what should be a cache hit")

    transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    monkeypatch.setattr(onnx_asr, "load_model", no_loading)
    transcribe(source, cache_dir=cache_dir)


def test_default_cache_is_a_per_user_klang_notes_folder(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """With no cache_dir, the Transcript lands in a klang-notes folder under the user's home."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    transcribe(source, recognize=TWO_SENTENCES)
    assert any(path.is_dir() for path in home.rglob("klang-notes"))


def test_cache_hit_returns_same_id(source: Path, cache_dir: Path):
    """A cache hit returns the ID of the first run."""
    first = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    second = transcribe(source, cache_dir=cache_dir, recognize=never_called)
    assert second.transcript_id == first.transcript_id


def test_cache_hit_reports_cached(source: Path, cache_dir: Path):
    """A cache hit reports cached=True."""
    transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    second = transcribe(source, cache_dir=cache_dir, recognize=never_called)
    assert second.cached is True


def test_cache_hit_reports_original_stats(source: Path, cache_dir: Path):
    """A cache hit reports the first run's duration, Segment count and transcription time."""
    first = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    second = transcribe(source, cache_dir=cache_dir, recognize=never_called)
    assert (second.duration_s, second.segment_count, second.transcription_s) == (
        first.duration_s,
        first.segment_count,
        first.transcription_s,
    )


def test_relative_path_hits_absolute_entry(source: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """A relative path and its absolute form share one cache entry."""
    first = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    monkeypatch.chdir(source.parent)
    second = transcribe("lecture.m4a", cache_dir=cache_dir, recognize=never_called)
    assert second.transcript_id == first.transcript_id


def test_tilde_path_hits_absolute_entry(source: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """A `~` path and its absolute form share one cache entry."""
    first = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    monkeypatch.setenv("HOME", str(source.parent.parent))
    second = transcribe("~/media/lecture.m4a", cache_dir=cache_dir, recognize=never_called)
    assert second.transcript_id == first.transcript_id


def test_changed_file_keeps_cached_transcript(source: Path, cache_dir: Path):
    """Replacing the file at a cached path still reads back the first Transcript."""
    first = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    before = get_transcript(first.transcript_id, cache_dir=cache_dir)
    shutil.copy(SILENCE, source)
    transcribe(source, cache_dir=cache_dir, recognize=never_called)
    assert get_transcript(first.transcript_id, cache_dir=cache_dir) == before


# Failures


def test_missing_path_raises_source_error_naming_it(tmp_path: Path, cache_dir: Path):
    """A path that doesn't exist raises SourceError whose message names the path."""
    missing = tmp_path / "nope.m4a"
    with pytest.raises(SourceError, match="nope.m4a"):
        transcribe(missing, cache_dir=cache_dir, recognize=TWO_SENTENCES)


def test_missing_path_is_not_cached(tmp_path: Path, cache_dir: Path):
    """After a missing-path error, a file later created there is transcribed fresh."""
    path = tmp_path / "later.m4a"
    with pytest.raises(SourceError):
        transcribe(path, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    shutil.copy(SPEECH, path)
    assert transcribe(path, cache_dir=cache_dir, recognize=TWO_SENTENCES).cached is False


def test_directory_raises_source_error_naming_it(tmp_path: Path, cache_dir: Path):
    """A path to a directory raises SourceError whose message names the path."""
    folder = tmp_path / "a_folder"
    folder.mkdir()
    with pytest.raises(SourceError, match="a_folder"):
        transcribe(folder, cache_dir=cache_dir, recognize=TWO_SENTENCES)


def test_undecodable_file_raises_source_error_naming_it(tmp_path: Path, cache_dir: Path):
    """A file ffmpeg can't decode raises SourceError whose message names the path."""
    broken = tmp_path / "broken.m4a"
    broken.write_text("not audio")
    with pytest.raises(SourceError, match="broken.m4a"):
        transcribe(broken, cache_dir=cache_dir, recognize=TWO_SENTENCES)


def test_undecodable_file_is_not_cached(tmp_path: Path, cache_dir: Path):
    """After a decode error, a real file put at the same path is transcribed fresh."""
    path = tmp_path / "broken.m4a"
    path.write_text("not audio")
    with pytest.raises(SourceError):
        transcribe(path, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    shutil.copy(SPEECH, path)
    assert transcribe(path, cache_dir=cache_dir, recognize=TWO_SENTENCES).cached is False


def test_no_fragments_raises_no_speech_error_naming_path(tmp_path: Path, cache_dir: Path):
    """A Source where the recognizer finds nothing raises NoSpeechError naming the path."""
    path = tmp_path / "quiet.m4a"
    shutil.copy(SILENCE, path)
    with pytest.raises(NoSpeechError, match="quiet.m4a"):
        transcribe(path, cache_dir=cache_dir, recognize=fake())


def test_only_empty_fragments_raises_no_speech_error(tmp_path: Path, cache_dir: Path):
    """A Source whose fragments are all whitespace raises NoSpeechError."""
    path = tmp_path / "quiet.m4a"
    shutil.copy(SILENCE, path)
    with pytest.raises(NoSpeechError):
        transcribe(path, cache_dir=cache_dir, recognize=fake(Fragment(0.0, 1.0, " "), Fragment(2.0, 2.5, "")))


def test_no_speech_source_is_not_cached(source: Path, cache_dir: Path):
    """After a NoSpeechError, the same path is transcribed fresh next time."""
    with pytest.raises(NoSpeechError):
        transcribe(source, cache_dir=cache_dir, recognize=fake())
    assert transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES).cached is False


def test_source_error_names_path_as_given(tmp_path: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """A SourceError names the path the caller passed, not its resolved form."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(SourceError, match="~/nope.m4a"):
        transcribe("~/nope.m4a", cache_dir=cache_dir, recognize=TWO_SENTENCES)


def test_missing_ffmpeg_raises_source_error(
    source: Path, tmp_path: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """With no ffmpeg on PATH, transcribe raises SourceError saying so."""
    empty = tmp_path / "empty_bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(SourceError, match="ffmpeg is not installed"):
        transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)


# YouTube Sources


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
        f"https://WWW.YouTube.com/watch?v={VIDEO_ID}",
    ],
)
def test_youtube_url_form_hits_canonical_entry(url: str, cache_dir: Path):
    """Every accepted URL form of a video hits the cache entry made from its canonical watch URL."""
    first = transcribe_url(WATCH_URL, cache_dir)
    assert transcribe_url(url, cache_dir, download=never_download).transcript_id == first.transcript_id


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


def test_unfetchable_video_raises_source_error(cache_dir: Path):
    """A video the downloader can't fetch raises SourceError out of transcribe."""
    with pytest.raises(SourceError, match=re.escape(WATCH_URL)):
        transcribe_url(f"https://youtu.be/{VIDEO_ID}", cache_dir, download=unfetchable)


def test_unfetchable_video_is_not_cached(cache_dir: Path):
    """After a failed download, the same video is transcribed fresh once it can be fetched."""
    with pytest.raises(SourceError):
        transcribe_url(WATCH_URL, cache_dir, download=unfetchable)
    assert transcribe_url(WATCH_URL, cache_dir).cached is False


def test_neither_file_nor_youtube_url_raises_source_error_saying_so(tmp_path: Path, cache_dir: Path):
    """A string that is neither an existing file nor a YouTube URL raises SourceError saying so."""
    with pytest.raises(SourceError, match="not a file or a YouTube URL"):
        transcribe(str(tmp_path / "nope.m4a"), cache_dir=cache_dir, recognize=TWO_SENTENCES, download=never_download)


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        "https://www.youtube.com/playlist?list=PLabcdefghijklmnop",
        "https://www.youtube.com/watch?list=PLabcdefghijklmnop",
        "https://www.youtube.com/watch?v=tooshort",
        f"https://vimeo.com/watch?v={VIDEO_ID}",
        f"ftp://youtu.be/{VIDEO_ID}",
        f"https://[youtu.be/{VIDEO_ID}",
    ],
)
def test_unaccepted_url_raises_source_error_saying_so(url: str, cache_dir: Path):
    """A URL outside the accepted YouTube forms raises the same error as a missing file, without downloading."""
    with pytest.raises(SourceError, match="not a file or a YouTube URL"):
        transcribe(url, cache_dir=cache_dir, recognize=TWO_SENTENCES, download=never_download)


# get_transcript


def test_get_transcript_returns_stamped_lines_in_time_order(source: Path, cache_dir: Path):
    """Read-back is one `[m:ss] text` line per Segment, in time order, joined by newlines."""
    result = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == (
        "[0:01] Idag ska vi prata om matriser.\n[1:05] En matris är en tabell."
    )


def test_get_transcript_rounds_stamps_down(source: Path, cache_dir: Path):
    """A Segment starting at 59.9 s reads `[0:59]`."""
    result = transcribe(source, cache_dir=cache_dir, recognize=fake(Fragment(59.9, 61.0, "Hej.")))
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == "[0:59] Hej."


def test_get_transcript_counts_minutes_past_an_hour(source: Path, cache_dir: Path):
    """A Segment starting at 4503.9 s reads `[75:03]`."""
    result = transcribe(source, cache_dir=cache_dir, recognize=fake(Fragment(4503.9, 4505.0, "Hej.")))
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == "[75:03] Hej."


def test_get_transcript_unknown_id_raises(cache_dir: Path):
    """An ID with no cached Transcript raises UnknownTranscriptError."""
    with pytest.raises(UnknownTranscriptError, match="deadbeef0000"):
        get_transcript("deadbeef0000", cache_dir=cache_dir)


def test_get_transcript_rejects_id_that_is_not_12_hex(tmp_path: Path, cache_dir: Path):
    """An ID outside the 12-hex form raises UnknownTranscriptError, even if a file sits at that name."""
    cache_dir.mkdir()
    (tmp_path / "outside.json").write_text("{}")
    with pytest.raises(UnknownTranscriptError):
        get_transcript("../outside", cache_dir=cache_dir)


# Real model


@pytest.mark.slow
def test_real_model_transcribes_swedish_speech(cache_dir: Path):
    """Pianissimo transcribes the Alva clip, and the read-back mentions matriser."""
    result = transcribe(SPEECH, cache_dir=cache_dir)
    assert "matris" in get_transcript(result.transcript_id, cache_dir=cache_dir).lower()


# Real downloader


@pytest.mark.network
def test_real_downloader_fetches_youtube_audio(cache_dir: Path):
    """The default downloader fetches a public video's audio, which then decodes to its full length."""
    result = transcribe(ZOO_VIDEO_URL, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    assert result.duration_s == pytest.approx(ZOO_DURATION_S, abs=1.5)


@pytest.mark.network
def test_real_downloader_writes_nothing_to_stdout(cache_dir: Path, capfd: pytest.CaptureFixture[str]):
    """The default downloader keeps stdout empty, since the stdio MCP server sends its messages there."""
    transcribe(ZOO_VIDEO_URL, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    assert capfd.readouterr().out == ""


@pytest.mark.network
def test_real_downloader_unavailable_video_raises_source_error_naming_url(cache_dir: Path):
    """The default downloader turns a video YouTube can't serve into SourceError naming its canonical URL."""
    with pytest.raises(SourceError, match=re.escape(f"https://www.youtube.com/watch?v={MISSING_VIDEO_ID}")):
        transcribe(MISSING_VIDEO_URL, cache_dir=cache_dir, recognize=TWO_SENTENCES)
