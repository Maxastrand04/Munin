"""Acceptance tests for #4: transcribe a local file and read it back through MCP."""

import asyncio
import hashlib
import shutil
import wave
from pathlib import Path

import pytest
from mcp import Client

from klang_notes.core import (
    Fragment,
    NoSpeechError,
    Segment,
    SourceError,
    UnknownTranscriptError,
    get_transcript,
    merge_fragments,
    transcribe,
)
from klang_notes.mcp_server import create_server

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


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A copy of the speech fixture in a temp folder, so a test may change it."""
    path = tmp_path / "media" / "lecture.m4a"
    path.parent.mkdir()
    shutil.copy(SPEECH, path)
    return path


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


# merge_fragments


def test_merge_drops_fragments_with_only_whitespace():
    """A fragment whose text is empty after strip() produces no Segment."""
    segments = merge_fragments([Fragment(0.0, 1.0, "Hej."), Fragment(5.0, 6.0, "   ")])
    assert segments == [Segment(0.0, 1.0, "Hej.")]


def test_merge_joins_fragment_after_text_without_end_punctuation():
    """A fragment joins the previous one, with one space, when the previous text has no end punctuation."""
    segments = merge_fragments([Fragment(0.0, 2.0, "Det första är"), Fragment(2.5, 4.0, "Matrisens storlek.")])
    assert segments == [Segment(0.0, 4.0, "Det första är Matrisens storlek.")]


def test_merge_joins_lowercase_fragment_after_period():
    """A fragment starting lowercase joins the previous one even when that ends in a period."""
    segments = merge_fragments([Fragment(0.0, 2.0, "Då säger man."), Fragment(2.5, 4.0, "att den är kvadratisk.")])
    assert segments == [Segment(0.0, 4.0, "Då säger man. att den är kvadratisk.")]


@pytest.mark.parametrize("end", [".", "?", "!"])
def test_merge_starts_new_segment_after_sentence_end(end: str):
    """An uppercase fragment after `.`, `?` or `!` starts a new Segment."""
    segments = merge_fragments([Fragment(0.0, 2.0, f"Det är bra{end}"), Fragment(2.5, 4.0, "Nästa sak.")])
    assert segments == [Segment(0.0, 2.0, f"Det är bra{end}"), Segment(2.5, 4.0, "Nästa sak.")]


def test_merge_joins_continuing_sentence_after_pause_just_under_limit():
    """A continuing fragment joins across a pause just under 1.5 s."""
    segments = merge_fragments([Fragment(0.0, 2.0, "Det första är"), Fragment(3.49, 5.0, "storleken.")])
    assert len(segments) == 1


def test_merge_splits_continuing_sentence_at_pause_of_1_5_s():
    """A continuing fragment after a pause of 1.5 s or more starts a new Segment."""
    segments = merge_fragments([Fragment(0.0, 2.0, "Det första är"), Fragment(3.5, 5.0, "storleken.")])
    assert len(segments) == 2


def test_merge_joins_when_result_is_exactly_20_s():
    """A continuing fragment joins when the joined Segment is exactly 20 s long."""
    segments = merge_fragments([Fragment(0.0, 10.0, "Det första är"), Fragment(10.5, 20.0, "storleken.")])
    assert segments == [Segment(0.0, 20.0, "Det första är storleken.")]


def test_merge_splits_when_result_would_exceed_20_s():
    """A continuing fragment starts a new Segment when joining would pass 20 s."""
    segments = merge_fragments([Fragment(0.0, 10.0, "Det första är"), Fragment(10.5, 20.5, "storleken.")])
    assert len(segments) == 2


def test_merge_keeps_single_long_fragment_whole():
    """A single fragment over 20 s becomes one Segment with its own times."""
    segments = merge_fragments([Fragment(3.0, 33.0, "En väldigt lång mening utan paus.")])
    assert segments == [Segment(3.0, 33.0, "En väldigt lång mening utan paus.")]


def test_merge_strips_segment_text():
    """Segment text carries no leading or trailing whitespace."""
    segments = merge_fragments([Fragment(0.0, 1.0, "  Hej.  ")])
    assert segments == [Segment(0.0, 1.0, "Hej.")]


def test_merge_of_no_fragments_is_empty():
    """An empty fragment list gives an empty Segment list."""
    assert merge_fragments([]) == []


# transcribe, fresh run


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


def test_transcribe_reports_non_negative_transcription_time(source: Path, cache_dir: Path):
    """transcription_s on a fresh run is a measured time, zero or more."""
    result = transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    assert result.transcription_s >= 0.0


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


# transcribe, cache hits


def test_cache_hit_does_not_run_recognizer(source: Path, cache_dir: Path):
    """A second call for the same Source never calls the recognizer."""
    transcribe(source, cache_dir=cache_dir, recognize=TWO_SENTENCES)
    transcribe(source, cache_dir=cache_dir, recognize=never_called)


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


# transcribe, failures


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


# MCP adapter


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def test_mcp_lists_both_tools(cache_dir: Path):
    """The server exposes `transcribe` and `get_transcript`."""

    async def run():
        async with Client(create_server(cache_dir=cache_dir, recognize=TWO_SENTENCES)) as client:
            return await client.list_tools()

    names = {tool.name for tool in asyncio.run(run()).tools}
    assert names == {"transcribe", "get_transcript"}


def test_mcp_transcribe_returns_result_fields(source: Path, cache_dir: Path):
    """The transcribe tool returns the five TranscribeResult fields."""
    server = create_server(cache_dir=cache_dir, recognize=TWO_SENTENCES)
    result = call(server, "transcribe", {"path": str(source)})
    assert set(result.structured_content) == {
        "transcript_id",
        "duration_s",
        "segment_count",
        "transcription_s",
        "cached",
    }


def test_mcp_get_transcript_returns_lines(source: Path, cache_dir: Path):
    """The get_transcript tool returns the same lines as the core."""
    server = create_server(cache_dir=cache_dir, recognize=TWO_SENTENCES)
    transcript_id = call(server, "transcribe", {"path": str(source)}).structured_content["transcript_id"]
    result = call(server, "get_transcript", {"transcript_id": transcript_id})
    assert result.content[0].text == get_transcript(transcript_id, cache_dir=cache_dir)


def test_mcp_unknown_id_is_tool_error(cache_dir: Path):
    """An unknown ID comes back as an MCP tool error."""
    server = create_server(cache_dir=cache_dir, recognize=TWO_SENTENCES)
    result = call(server, "get_transcript", {"transcript_id": "deadbeef0000"})
    assert result.is_error is True


def test_mcp_tool_error_carries_core_message(tmp_path: Path, cache_dir: Path):
    """A core error's message reaches the LLM in the tool error."""
    server = create_server(cache_dir=cache_dir, recognize=TWO_SENTENCES)
    result = call(server, "transcribe", {"path": str(tmp_path / "nope.m4a")})
    assert "nope.m4a" in result.content[0].text


# Real model


@pytest.mark.slow
def test_real_model_transcribes_swedish_speech(cache_dir: Path):
    """Pianissimo transcribes the Alva clip, and the read-back mentions matriser."""
    result = transcribe(SPEECH, cache_dir=cache_dir)
    assert "matris" in get_transcript(result.transcript_id, cache_dir=cache_dir).lower()
