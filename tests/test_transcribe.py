import hashlib
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
    get_transcript,
    transcribe,
)

FIXTURES = Path(__file__).parent / "fixtures"
SPEECH = FIXTURES / "sv_short.m4a"
SPEECH_DURATION_S = 4.30
SILENCE = FIXTURES / "silence.m4a"


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
