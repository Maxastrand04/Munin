import hashlib
import json
import re
import shutil
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import onnx_asr
import pytest

from munin.core import (
    Fragment,
    KthPlaySource,
    LanguageError,
    NoSpeechError,
    SourceError,
    UnknownTranscriptError,
    Video,
    Vocabulary,
    YouTubeSource,
    get_transcript,
    read_slides,
    render_mindmap,
    transcribe,
)

FIXTURES = Path(__file__).parent / "fixtures"
SPEECH = FIXTURES / "sv_short.m4a"
SPEECH_EN = FIXTURES / "en_short.m4a"
SPEECH_DURATION_S = 4.30
SILENCE = FIXTURES / "silence.m4a"

PIANISSIMO = "KlangAI/pianissimo-sv-onnx"
PARAKEET = "istupakov/parakeet-tdt-0.6b-v3-onnx"
BAD_LANGUAGES = ["de", "", "EN", "english", "sv "]

VIDEO_ID = "dQw4w9WgXcQ"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
ZOO_VIDEO_URL = "https://youtu.be/jNQXAC9IVRw"
ZOO_DURATION_S = 19
MISSING_VIDEO_ID = "zzzzzzzzzz0"
MISSING_VIDEO_URL = f"https://youtu.be/{MISSING_VIDEO_ID}"

ENTRY_ID = "0_1zk8obn5"
FIXED_URL = f"https://play.kth.se/media/t/{ENTRY_ID}"
SLUG_URL = f"https://play.kth.se/media/Föreläsning+4A+Matriser/{ENTRY_ID}"
SHORT_ENTRY_ID = "0_kcveux4p"
SHORT_DURATION_S = 16.4
MISSING_ENTRY_ID = "0_zzzzzzzz"


def fake(*fragments: Fragment, received: list | None = None):
    """A recognizer that ignores the audio, records each Vocabulary it gets in `received`, and yields the given fragments."""

    def recognize(wav: Path, vocabulary: Vocabulary | None):
        if received is not None:
            received.append(vocabulary)
        return list(fragments)

    return recognize


def never_called(wav: Path, vocabulary: Vocabulary | None):
    raise AssertionError("the recognizer ran on what should be a cache hit")


TWO_SENTENCES = fake(
    Fragment(1.2, 3.0, "Idag ska vi prata om matriser."),
    Fragment(65.7, 68.0, "En matris är en tabell."),
)

GAUSS = Vocabulary(["Gausselimination"])
SWEDISH = fake(Fragment(1.2, 3.0, "Idag ska vi prata om matriser."))
ENGLISH = fake(Fragment(1.2, 3.0, "Today we talk about processes."))
SWEDISH_LINE = "[0:01] Idag ska vi prata om matriser."
ENGLISH_LINE = "[0:01] Today we talk about processes."
PLAIN_GAUSS = Fragment(1.2, 3.0, "Idag ska vi prata om gauss elimination.")
BOOSTED_GAUSS = Fragment(1.2, 3.0, "Idag ska vi prata om Gausselimination.")


def fake_download(calls: list | None = None, written: list | None = None):
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""

    def download(video: Video, workdir: Path) -> Path:
        if calls is not None:
            calls.append(video)
        audio = workdir / "audio.m4a"
        shutil.copy(SPEECH, audio)
        if written is not None:
            written.append(audio)
        return audio

    return download


def never_download(video: Video, workdir: Path) -> Path:
    raise AssertionError("the downloader ran on what should be a cache hit or a non-video Source")


def unfetchable(video: Video, workdir: Path) -> Path:
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

    def slow_recognize(wav: Path, vocabulary: Vocabulary | None):
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

    def recognize(wav: Path, vocabulary: Vocabulary | None):
        with wave.open(str(wav)) as w:
            rates.append(w.getframerate())
        return [Fragment(0.0, 1.0, "Hej.")]

    transcribe(source, cache_dir=cache_dir, recognize=recognize)
    assert rates == [16000]


def test_recognizer_gets_mono_audio(source: Path, cache_dir: Path):
    """The recognizer receives a wav with one channel."""
    channels = []

    def recognize(wav: Path, vocabulary: Vocabulary | None):
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


def test_default_cache_is_a_per_user_munin_folder(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """With no cache_dir, the Transcript lands in a munin folder under the user's home."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    transcribe(source, recognize=TWO_SENTENCES)
    assert any(path.is_dir() for path in home.rglob("munin"))


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


# Vocabulary


def test_recognizer_gets_vocabulary_terms_unchanged(source: Path, cache_dir: Path):
    """The recognizer receives the Vocabulary's terms with their capitalisation unchanged."""
    received = []
    vocabulary = Vocabulary(["SF1624", "Gausselimination"])
    transcribe(source, vocabulary=vocabulary, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS, received=received))
    assert received[0].terms == ("SF1624", "Gausselimination")


def test_recognizer_gets_vocabulary_alpha(source: Path, cache_dir: Path):
    """The recognizer receives the Vocabulary's boost strength."""
    received = []
    vocabulary = Vocabulary(["Gauss"], 1.7)
    transcribe(source, vocabulary=vocabulary, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS, received=received))
    assert received[0].alpha == 1.7


def test_recognizer_gets_none_without_vocabulary(source: Path, cache_dir: Path):
    """A fresh run without a Vocabulary passes None to the recognizer."""
    received = []
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS, received=received))
    assert received == [None]


def test_blank_vocabulary_reaches_recognizer_as_none(source: Path, cache_dir: Path):
    """A Vocabulary whose terms are all blank counts as none, so the recognizer gets None."""
    received = []
    vocabulary = Vocabulary(["  ", ""])
    transcribe(source, vocabulary=vocabulary, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS, received=received))
    assert received == [None]


def test_vocabulary_reruns_cached_source(source: Path, cache_dir: Path):
    """A call with a Vocabulary runs the recognizer even when the Source is cached."""
    received = []
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS))
    transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS, received=received))
    assert received == [GAUSS]


def test_vocabulary_run_keeps_transcript_id(source: Path, cache_dir: Path):
    """A boosted rerun of a cached Source returns the same Transcript ID."""
    first = transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS))
    second = transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS))
    assert second.transcript_id == first.transcript_id


def test_vocabulary_run_reports_not_cached(source: Path, cache_dir: Path):
    """A boosted rerun of a cached Source reports cached=False."""
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS))
    result = transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS))
    assert result.cached is False


def test_vocabulary_run_replaces_cached_transcript(source: Path, cache_dir: Path):
    """After a boosted rerun, the read-back returns the boosted Transcript's lines."""
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS))
    result = transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS))
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == "[0:01] Idag ska vi prata om Gausselimination."


def test_vocabulary_run_reports_vocabulary(source: Path, cache_dir: Path):
    """A boosted run's stats include the Vocabulary it used."""
    result = transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS))
    assert result.vocabulary == GAUSS


def test_plain_run_reports_no_vocabulary(source: Path, cache_dir: Path):
    """A run without a Vocabulary reports vocabulary None."""
    result = transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS))
    assert result.vocabulary is None


def test_call_without_vocabulary_returns_boosted_transcript_without_running_model(source: Path, cache_dir: Path):
    """After a boosted run, a call without a Vocabulary is a cache hit that never runs the recognizer."""
    transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS))
    result = transcribe(source, cache_dir=cache_dir, recognize=never_called)
    assert result.cached is True


def test_cache_hit_after_vocabulary_run_reports_stored_vocabulary(source: Path, cache_dir: Path):
    """A cache hit on a boosted Transcript reports the Vocabulary it was made with."""
    transcribe(source, vocabulary=Vocabulary(["Gausselimination"], 0.5), cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS))
    result = transcribe(source, cache_dir=cache_dir, recognize=never_called)
    assert result.vocabulary == Vocabulary(["Gausselimination"], 0.5)


def test_blank_vocabulary_on_cached_source_is_a_cache_hit(source: Path, cache_dir: Path):
    """A Vocabulary with only blank terms on a cached Source returns the cached Transcript without running the recognizer."""
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS))
    result = transcribe(source, vocabulary=Vocabulary(["  "]), cache_dir=cache_dir, recognize=never_called)
    assert result.cached is True


def test_vocabulary_run_keeps_the_deck(source: Path, deck: Path, cache_dir: Path, tmp_path: Path):
    """A boosted rerun of a Source keeps its Transcript's Deck attached, so a Slide number still renders."""
    transcript_id = transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS)).transcript_id
    read_slides(transcript_id, deck, cache_dir=cache_dir)
    transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS))
    gauss = {"type": "topic", "label": "Gauss", "explanation": "", "stamps": [], "slides": [2], "children": []}
    outline = {"type": "main-topic", "label": "Matriser", "explanation": "", "stamps": [], "slides": [], "children": [gauss]}
    assert render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out").page.is_file()


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


def test_failed_vocabulary_run_keeps_previous_transcript(source: Path, cache_dir: Path):
    """A boosted run that finds no speech leaves the previously cached Transcript in place."""
    first = transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS))
    with pytest.raises(NoSpeechError):
        transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake())
    assert get_transcript(first.transcript_id, cache_dir=cache_dir) == "[0:01] Idag ska vi prata om gauss elimination."


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


def test_youtube_vocabulary_reruns_cached_video(cache_dir: Path):
    """A boosted call on a cached YouTube Source downloads the video again."""
    calls: list = []
    transcribe_url(WATCH_URL, cache_dir)
    transcribe(WATCH_URL, vocabulary=GAUSS, cache_dir=cache_dir, recognize=TWO_SENTENCES, download=fake_download(calls=calls))
    assert len(calls) == 1


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

    def slow_download(video: Video, workdir: Path) -> Path:
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
    with pytest.raises(SourceError, match="not a file, a YouTube URL or a KTH Play video URL"):
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
    with pytest.raises(SourceError, match="not a file, a YouTube URL or a KTH Play video URL"):
        transcribe(url, cache_dir=cache_dir, recognize=TWO_SENTENCES, download=never_download)


# KTH Play Sources


def test_kthplay_url_miss_is_transcribed_fresh(cache_dir: Path):
    """A KTH Play link seen for the first time is transcribed, not served from the cache."""
    assert transcribe_url(SLUG_URL, cache_dir).cached is False


def test_kthplay_url_miss_downloads_the_parsed_video(cache_dir: Path):
    """The downloader is asked for the KTH Play video the link points at."""
    calls: list = []
    transcribe_url(SLUG_URL, cache_dir, download=fake_download(calls=calls))
    assert calls == [KthPlaySource(ENTRY_ID)]


def test_kthplay_transcript_id_is_sha256_prefix_of_fixed_address(cache_dir: Path):
    """A KTH Play Transcript's ID is the first 12 hex characters of the SHA-256 of the fixed lecture address."""
    expected = hashlib.sha256(FIXED_URL.encode()).hexdigest()[:12]
    assert transcribe_url(SLUG_URL, cache_dir).transcript_id == expected


def test_kthplay_cache_hit_does_not_download(cache_dir: Path):
    """A second call for the same KTH Play video returns the saved Transcript without downloading."""
    transcribe_url(SLUG_URL, cache_dir)
    assert transcribe_url(SLUG_URL, cache_dir, download=never_download).cached is True


@pytest.mark.parametrize(
    "url",
    [
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
    ],
)
def test_kthplay_url_form_shares_one_transcript(url: str, cache_dir: Path):
    """Every accepted link form of a KTH Play video hits the Transcript made from another form."""
    first = transcribe_url(SLUG_URL, cache_dir)
    assert transcribe_url(url, cache_dir, download=never_download).transcript_id == first.transcript_id


def test_downloaded_kthplay_video_is_deleted(cache_dir: Path):
    """After a KTH Play miss, the file the downloader wrote no longer exists."""
    written: list = []
    transcribe_url(SLUG_URL, cache_dir, download=fake_download(written=written))
    assert not written[0].exists()


def test_kthplay_vocabulary_reruns_cached_video(cache_dir: Path):
    """A boosted call on a cached KTH Play Source downloads the video again."""
    calls: list = []
    transcribe_url(SLUG_URL, cache_dir)
    transcribe(SLUG_URL, vocabulary=GAUSS, cache_dir=cache_dir, recognize=TWO_SENTENCES, download=fake_download(calls=calls))
    assert len(calls) == 1


def test_kthplay_vocabulary_run_keeps_transcript_id(cache_dir: Path):
    """A boosted run replaces the saved KTH Play Transcript under the same ID."""
    first = transcribe_url(SLUG_URL, cache_dir)
    second = transcribe(SLUG_URL, vocabulary=GAUSS, cache_dir=cache_dir, recognize=TWO_SENTENCES, download=fake_download())
    assert second.transcript_id == first.transcript_id


def test_kthplay_vocabulary_run_replaces_cached_transcript(cache_dir: Path):
    """After a boosted run on a KTH Play Source, its saved Transcript reads back as the boosted text."""
    transcribe(SLUG_URL, cache_dir=cache_dir, recognize=fake(PLAIN_GAUSS), download=fake_download())
    result = transcribe(SLUG_URL, vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS), download=fake_download())
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == "[0:01] Idag ska vi prata om Gausselimination."


def test_unfetchable_kthplay_video_raises_source_error_naming_fixed_address(cache_dir: Path):
    """A KTH Play video the downloader can't fetch raises SourceError naming the fixed lecture address."""
    with pytest.raises(SourceError, match=re.escape(FIXED_URL)):
        transcribe_url(SLUG_URL, cache_dir, download=unfetchable)


def test_unfetchable_kthplay_video_is_not_cached(cache_dir: Path):
    """After a failed KTH Play download, the same video is transcribed fresh once it can be fetched."""
    with pytest.raises(SourceError):
        transcribe_url(SLUG_URL, cache_dir, download=unfetchable)
    assert transcribe_url(SLUG_URL, cache_dir).cached is False


def test_silent_kthplay_video_raises_no_speech_error(cache_dir: Path):
    """A KTH Play video with no speech raises NoSpeechError."""
    with pytest.raises(NoSpeechError):
        transcribe(SLUG_URL, cache_dir=cache_dir, recognize=fake(), download=fake_download())


def test_silent_kthplay_video_is_not_cached(cache_dir: Path):
    """After a KTH Play video yields no speech, the same video is transcribed fresh next time."""
    with pytest.raises(NoSpeechError):
        transcribe(SLUG_URL, cache_dir=cache_dir, recognize=fake(), download=fake_download())
    assert transcribe_url(SLUG_URL, cache_dir).cached is False


def test_non_video_kthplay_link_raises_source_error_saying_so(cache_dir: Path):
    """A play.kth.se link outside the three video shapes fails like any unrecognised input, without downloading."""
    with pytest.raises(SourceError, match="not a file, a YouTube URL or a KTH Play video URL"):
        transcribe("https://play.kth.se/channel/SF1624/123456", cache_dir=cache_dir, recognize=TWO_SENTENCES, download=never_download)


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


# Language


def write_entry_without_language(source: Path, cache_dir: Path) -> str:
    """Write a cache file for `source` with no `language` key, and return its Transcript ID."""
    resolved = str(source.resolve())
    transcript_id = hashlib.sha256(resolved.encode()).hexdigest()[:12]
    cache_dir.mkdir(parents=True, exist_ok=True)
    stored = {
        "source": resolved,
        "duration_s": 4.3,
        "transcription_s": 1.0,
        "segments": [{"start": 1.2, "end": 3.0, "text": "Idag ska vi prata om matriser."}],
        "vocabulary": None,
    }
    (cache_dir / f"{transcript_id}.json").write_text(json.dumps(stored), encoding="utf-8")
    return transcript_id


def test_english_call_on_a_miss_loads_only_parakeet(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A call with `en` and nothing cached loads Parakeet and never Pianissimo."""
    transcribe(source, language="en", cache_dir=cache_dir)
    assert speech_library.repos == [PARAKEET]


def test_swedish_call_on_a_miss_loads_only_pianissimo(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A call with `sv` and nothing cached loads Pianissimo and never Parakeet."""
    transcribe(source, language="sv", cache_dir=cache_dir)
    assert speech_library.repos == [PIANISSIMO]


def test_call_with_no_language_on_a_miss_loads_pianissimo(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A call with no language and nothing cached loads Pianissimo."""
    transcribe(source, cache_dir=cache_dir)
    assert speech_library.repos == [PIANISSIMO]


def test_call_with_no_language_on_a_miss_reports_swedish(source: Path, cache_dir: Path):
    """A call with no language and nothing cached reports `sv`."""
    assert transcribe(source, cache_dir=cache_dir, recognize=SWEDISH).language == "sv"


def test_english_run_reports_english(source: Path, cache_dir: Path):
    """The result of an `en` run reports language `en`."""
    assert transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH).language == "en"


def test_english_run_is_not_cached(source: Path, cache_dir: Path):
    """A first `en` run reports cached=False."""
    assert transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH).cached is False


def test_english_run_reads_back_its_text(source: Path, cache_dir: Path):
    """The English Transcript reads back through `get_transcript`."""
    result = transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == ENGLISH_LINE


def test_english_fragments_go_through_the_merge_rule(source: Path, cache_dir: Path):
    """Fragments of one unfinished English sentence merge into one Segment, as Swedish ones do."""
    recognize = fake(Fragment(0.0, 1.0, "The first part is"), Fragment(1.2, 2.0, "the size."))
    assert transcribe(source, language="en", cache_dir=cache_dir, recognize=recognize).segment_count == 1


def test_english_run_from_youtube_reports_english(cache_dir: Path):
    """A YouTube Source runs in English too."""
    result = transcribe(WATCH_URL, language="en", cache_dir=cache_dir, recognize=ENGLISH, download=fake_download())
    assert result.language == "en"


def test_english_run_from_kthplay_reports_english(cache_dir: Path):
    """A KTH Play Source runs in English too."""
    result = transcribe(FIXED_URL, language="en", cache_dir=cache_dir, recognize=ENGLISH, download=fake_download())
    assert result.language == "en"


def test_no_language_returns_cached_english_as_english(source: Path, cache_dir: Path):
    """A call with no language on a cached English Transcript reports `en`."""
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).language == "en"


def test_no_language_on_cached_english_is_a_cache_hit(source: Path, cache_dir: Path):
    """A call with no language on a cached English Transcript reports cached=True."""
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).cached is True


def test_no_language_on_cached_english_loads_no_model(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A call with no language on a cached English Transcript loads no speech model."""
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    transcribe(source, cache_dir=cache_dir)
    assert speech_library.repos == []


def test_no_language_returns_cached_swedish_as_swedish(source: Path, cache_dir: Path):
    """A call with no language on a cached Swedish Transcript reports `sv`."""
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).language == "sv"


@pytest.mark.parametrize("language", ["sv", "en"])
def test_same_language_is_a_cache_hit(language: str, source: Path, cache_dir: Path):
    """A call with the cached Transcript's language reports cached=True."""
    transcribe(source, language=language, cache_dir=cache_dir, recognize=SWEDISH)
    assert transcribe(source, language=language, cache_dir=cache_dir, recognize=never_called).cached is True


@pytest.mark.parametrize("language", ["sv", "en"])
def test_same_language_loads_no_model(language: str, source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A call with the cached Transcript's language loads no speech model."""
    transcribe(source, language=language, cache_dir=cache_dir, recognize=SWEDISH)
    transcribe(source, language=language, cache_dir=cache_dir)
    assert speech_library.repos == []


def test_same_language_does_not_download(cache_dir: Path):
    """A call with a cached video's language never calls the downloader."""
    transcribe(WATCH_URL, language="en", cache_dir=cache_dir, recognize=ENGLISH, download=fake_download())
    transcribe(WATCH_URL, language="en", cache_dir=cache_dir, recognize=never_called, download=never_download)


def test_same_language_keeps_a_boosted_transcripts_vocabulary(source: Path, cache_dir: Path):
    """A `sv` call with no terms on a boosted Swedish Transcript returns it with its Vocabulary."""
    transcribe(source, language="sv", vocabulary=GAUSS, cache_dir=cache_dir, recognize=SWEDISH)
    assert transcribe(source, language="sv", cache_dir=cache_dir, recognize=never_called).vocabulary == GAUSS


def test_english_over_swedish_runs_parakeet(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """An `en` call on a cached Swedish Transcript loads Parakeet and never Pianissimo."""
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    transcribe(source, language="en", cache_dir=cache_dir)
    assert speech_library.repos == [PARAKEET]


def test_swedish_over_english_runs_pianissimo(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A `sv` call on a cached English Transcript loads Pianissimo and never Parakeet."""
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    transcribe(source, language="sv", cache_dir=cache_dir)
    assert speech_library.repos == [PIANISSIMO]


def test_different_language_reports_not_cached(source: Path, cache_dir: Path):
    """A call in another language reports cached=False."""
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    assert transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH).cached is False


def test_different_language_keeps_the_transcript_id(source: Path, cache_dir: Path):
    """A call in another language returns the same Transcript ID."""
    first = transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    second = transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    assert second.transcript_id == first.transcript_id


def test_different_language_replaces_the_text(source: Path, cache_dir: Path):
    """After a call in another language, the Transcript reads back as the new run's text."""
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    result = transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == ENGLISH_LINE


def test_different_language_replaces_the_stored_language(source: Path, cache_dir: Path):
    """After a call in another language, a call with no language reports the new one."""
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).language == "sv"


def test_different_language_drops_the_old_vocabulary(source: Path, cache_dir: Path):
    """An `en` run over a boosted Swedish Transcript stores no Vocabulary."""
    transcribe(source, language="sv", vocabulary=GAUSS, cache_dir=cache_dir, recognize=SWEDISH)
    assert transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH).vocabulary is None


def test_different_language_downloads_a_cached_video_again(cache_dir: Path):
    """A call in another language on a cached video downloads it again."""
    calls: list = []
    transcribe(WATCH_URL, language="sv", cache_dir=cache_dir, recognize=SWEDISH, download=fake_download())
    transcribe(WATCH_URL, language="en", cache_dir=cache_dir, recognize=ENGLISH, download=fake_download(calls=calls))
    assert len(calls) == 1


def test_different_language_keeps_the_deck(source: Path, deck: Path, cache_dir: Path, tmp_path: Path):
    """A call in another language keeps the Deck attached, so a Slide number still renders."""
    transcript_id = transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH).transcript_id
    read_slides(transcript_id, deck, cache_dir=cache_dir)
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    topic = {"type": "topic", "label": "Processes", "explanation": "", "stamps": [], "slides": [2], "children": []}
    outline = {"type": "main-topic", "label": "OS", "explanation": "", "stamps": [], "slides": [], "children": [topic]}
    assert render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out").page.is_file()


def test_entry_without_a_language_counts_as_swedish(source: Path, cache_dir: Path):
    """A cache file with no language reports `sv`."""
    write_entry_without_language(source, cache_dir)
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).language == "sv"


def test_entry_without_a_language_is_a_cache_hit_for_swedish(source: Path, cache_dir: Path):
    """A `sv` call on a cache file with no language reports cached=True."""
    write_entry_without_language(source, cache_dir)
    assert transcribe(source, language="sv", cache_dir=cache_dir, recognize=never_called).cached is True


def test_entry_without_a_language_is_replaced_by_english(source: Path, cache_dir: Path):
    """An `en` call on a cache file with no language runs English under the same ID."""
    transcript_id = write_entry_without_language(source, cache_dir)
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    assert get_transcript(transcript_id, cache_dir=cache_dir) == ENGLISH_LINE


def test_vocabulary_on_an_entry_without_a_language_reruns_swedish(source: Path, cache_dir: Path):
    """Terms and no language on a cache file with no language rerun Swedish and report `sv`."""
    write_entry_without_language(source, cache_dir)
    assert transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=SWEDISH).language == "sv"


@pytest.mark.parametrize("language", BAD_LANGUAGES)
def test_bad_language_raises_language_error(language: str, source: Path, cache_dir: Path):
    """Anything but an exact `sv` or `en` raises LanguageError."""
    with pytest.raises(LanguageError):
        transcribe(source, language=language, cache_dir=cache_dir, recognize=never_called)


def test_bad_language_fails_before_download(cache_dir: Path):
    """A bad language on a video raises LanguageError without calling the downloader."""
    with pytest.raises(LanguageError):
        transcribe(WATCH_URL, language="de", cache_dir=cache_dir, download=never_download)


def test_bad_language_loads_no_model(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A bad language raises LanguageError before either speech model loads."""
    with pytest.raises(LanguageError):
        transcribe(source, language="de", cache_dir=cache_dir)
    assert speech_library.repos == []


def test_bad_language_writes_nothing(source: Path, cache_dir: Path):
    """A bad language caches nothing, so the next plain call transcribes fresh."""
    with pytest.raises(LanguageError):
        transcribe(source, language="de", cache_dir=cache_dir, recognize=never_called)
    assert transcribe(source, cache_dir=cache_dir, recognize=SWEDISH).cached is False


def test_bad_language_on_a_cached_source_still_raises(source: Path, cache_dir: Path):
    """A bad language on a cached Source raises LanguageError rather than returning the cached Transcript."""
    transcribe(source, cache_dir=cache_dir, recognize=SWEDISH)
    with pytest.raises(LanguageError):
        transcribe(source, language="de", cache_dir=cache_dir, recognize=never_called)


def test_english_with_terms_raises(source: Path, cache_dir: Path):
    """Terms with `en` raise EnglishVocabularyError."""
    with pytest.raises(EnglishVocabularyError):
        transcribe(source, language="en", vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called)


def test_english_vocabulary_error_says_what_to_do(source: Path, cache_dir: Path):
    """The error tells the caller to call again without terms."""
    with pytest.raises(EnglishVocabularyError, match="Call again without them"):
        transcribe(source, language="en", vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called)


def test_english_with_terms_fails_before_download(cache_dir: Path):
    """Terms with `en` on a video raise without calling the downloader."""
    with pytest.raises(EnglishVocabularyError):
        transcribe(WATCH_URL, language="en", vocabulary=GAUSS, cache_dir=cache_dir, download=never_download)


def test_english_with_terms_writes_nothing(source: Path, cache_dir: Path):
    """Terms with `en` cache nothing, so the next plain call transcribes fresh."""
    with pytest.raises(EnglishVocabularyError):
        transcribe(source, language="en", vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called)
    assert transcribe(source, cache_dir=cache_dir, recognize=SWEDISH).cached is False


def test_english_with_terms_leaves_a_swedish_transcript(source: Path, cache_dir: Path):
    """Terms with `en` on a cached Swedish Transcript leave its text in place."""
    result = transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    with pytest.raises(EnglishVocabularyError):
        transcribe(source, language="en", vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called)
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == SWEDISH_LINE


def test_terms_with_no_language_on_cached_english_raise(source: Path, cache_dir: Path):
    """Terms with no language on a cached English Transcript raise EnglishVocabularyError."""
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    with pytest.raises(EnglishVocabularyError):
        transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called)


def test_terms_with_no_language_on_cached_english_leave_it(source: Path, cache_dir: Path):
    """Terms with no language on a cached English Transcript leave its text in place."""
    result = transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    with pytest.raises(EnglishVocabularyError):
        transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called)
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == ENGLISH_LINE


def test_blank_vocabulary_on_english_reaches_recognizer_as_none(source: Path, cache_dir: Path):
    """A Vocabulary whose terms are all blank is no Vocabulary, so an `en` run goes ahead with None."""
    received = []
    recognize = fake(Fragment(1.2, 3.0, "Hello there."), received=received)
    transcribe(source, language="en", vocabulary=Vocabulary(["  "]), cache_dir=cache_dir, recognize=recognize)
    assert received == [None]


def test_swedish_terms_reach_the_recognizer(source: Path, cache_dir: Path):
    """Terms with `sv` reach the recognizer unchanged."""
    received = []
    transcribe(source, language="sv", vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS, received=received))
    assert received == [GAUSS]


def test_swedish_terms_rerun_a_cached_swedish_transcript(source: Path, cache_dir: Path):
    """Terms with `sv` on a cached Swedish Transcript run again."""
    received = []
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    transcribe(source, language="sv", vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS, received=received))
    assert received == [GAUSS]


def test_swedish_terms_replace_a_cached_english_transcript(source: Path, cache_dir: Path):
    """Terms with `sv` on a cached English Transcript run Swedish with those terms."""
    received = []
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    transcribe(source, language="sv", vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(BOOSTED_GAUSS, received=received))
    assert received == [GAUSS]


def test_terms_with_no_language_on_a_miss_run_swedish(source: Path, cache_dir: Path):
    """Terms with no language and nothing cached run Swedish and report `sv`."""
    assert transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=SWEDISH).language == "sv"


def test_terms_with_no_language_on_cached_swedish_stay_swedish(source: Path, cache_dir: Path):
    """Terms with no language on a cached Swedish Transcript rerun it and report `sv`."""
    transcribe(source, cache_dir=cache_dir, recognize=SWEDISH)
    assert transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=SWEDISH).language == "sv"


def test_failed_english_run_leaves_swedish_text(source: Path, cache_dir: Path):
    """An `en` run that finds no speech leaves the Swedish Transcript's text in place."""
    result = transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    with pytest.raises(NoSpeechError):
        transcribe(source, language="en", cache_dir=cache_dir, recognize=fake())
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == SWEDISH_LINE


def test_failed_english_run_leaves_swedish_language(source: Path, cache_dir: Path):
    """An `en` run that finds no speech leaves the stored language at `sv`."""
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    with pytest.raises(NoSpeechError):
        transcribe(source, language="en", cache_dir=cache_dir, recognize=fake())
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).language == "sv"


def test_failed_download_in_another_language_leaves_the_cached_transcript(cache_dir: Path):
    """An `en` run whose download fails leaves the Swedish Transcript's text in place."""
    result = transcribe(WATCH_URL, language="sv", cache_dir=cache_dir, recognize=SWEDISH, download=fake_download())
    with pytest.raises(SourceError):
        transcribe(WATCH_URL, language="en", cache_dir=cache_dir, recognize=ENGLISH, download=unfetchable)
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == SWEDISH_LINE


def test_failed_first_english_run_is_not_cached(source: Path, cache_dir: Path):
    """An `en` run that finds no speech caches nothing, so the next plain call transcribes fresh."""
    with pytest.raises(NoSpeechError):
        transcribe(source, language="en", cache_dir=cache_dir, recognize=fake())
    assert transcribe(source, cache_dir=cache_dir, recognize=SWEDISH).cached is False


# Real model


@pytest.mark.slow
def test_real_model_transcribes_swedish_speech(cache_dir: Path):
    """Pianissimo transcribes the Alva clip, and the read-back mentions matriser."""
    result = transcribe(SPEECH, cache_dir=cache_dir)
    assert "matris" in get_transcript(result.transcript_id, cache_dir=cache_dir).lower()


@pytest.mark.slow
def test_real_model_transcribes_with_vocabulary(cache_dir: Path):
    """Pianissimo spells the Alva clip's "matris" as "matrix" when that term is boosted at full strength, which it never writes unboosted."""
    result = transcribe(SPEECH, vocabulary=Vocabulary(["matrix"], 2.0), cache_dir=cache_dir)
    assert "matrix" in get_transcript(result.transcript_id, cache_dir=cache_dir)


@pytest.mark.slow
def test_real_model_transcribes_english_speech(cache_dir: Path):
    """Parakeet transcribes the English clip, opening with "Today", a word Pianissimo drops from it."""
    result = transcribe(SPEECH_EN, language="en", cache_dir=cache_dir)
    assert "today we will talk" in get_transcript(result.transcript_id, cache_dir=cache_dir).lower()


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


@pytest.mark.network
def test_real_kthplay_downloader_fetches_full_length_video(cache_dir: Path):
    """The default KTH Play downloader's file decodes to the video's full length."""
    result = transcribe(f"https://play.kth.se/media/t/{SHORT_ENTRY_ID}", cache_dir=cache_dir, recognize=TWO_SENTENCES)
    assert result.duration_s == pytest.approx(SHORT_DURATION_S, abs=1.5)


@pytest.mark.network
def test_real_kthplay_downloader_missing_entry_raises_source_error_naming_fixed_address(cache_dir: Path):
    """The default KTH Play downloader turns an entry KTH Play can't serve into SourceError naming its fixed lecture address and the download's reason."""
    with pytest.raises(SourceError, match=re.escape(f"https://play.kth.se/media/t/{MISSING_ENTRY_ID}") + ": .+"):
        transcribe(f"https://play.kth.se/media/t/{MISSING_ENTRY_ID}", cache_dir=cache_dir, recognize=TWO_SENTENCES)
