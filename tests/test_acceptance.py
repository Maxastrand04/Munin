import asyncio
import shutil
from pathlib import Path

import pytest
from mcp import Client

from munin.core import (
    Fragment,
    NoSpeechError,
    Vocabulary,
    VocabularyError,
    YouTubeSource,
    get_transcript,
    transcribe,
)
from munin.mcp_server import create_server

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

PLAIN = [Fragment(1.2, 3.0, "Idag ska vi prata om gauss elimination.")]
BOOSTED = [Fragment(1.2, 3.0, "Idag ska vi prata om Gausselimination.")]


def gauss() -> Vocabulary:
    """A one-term Vocabulary at the default strength."""
    return Vocabulary(["Gausselimination"])


def fake(fragments: list[Fragment], received: list | None = None):
    """A recognizer that ignores the audio, records each Vocabulary it gets, and yields `fragments`."""

    def recognize(wav: Path, vocabulary: Vocabulary | None):
        if received is not None:
            received.append(vocabulary)
        return list(fragments)

    return recognize


def never_called(wav: Path, vocabulary: Vocabulary | None):
    raise AssertionError("the recognizer ran on what should be a cache hit")


def fake_download(calls: list | None = None):
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""

    def download(video: YouTubeSource, workdir: Path) -> Path:
        if calls is not None:
            calls.append(video)
        audio = workdir / "audio.m4a"
        shutil.copy(SPEECH, audio)
        return audio

    return download


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def transcribe_description(server) -> str:
    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    return next(tool.description for tool in asyncio.run(run()).tools if tool.name == "transcribe")


# Vocabulary


def test_vocabulary_keeps_term_capitalisation():
    """Terms keep their capitalisation exactly as given."""
    assert Vocabulary(["SF1624", "Gausselimination", "pivotElement"]).terms == (
        "SF1624",
        "Gausselimination",
        "pivotElement",
    )


def test_vocabulary_strips_terms():
    """Whitespace around a term is stripped."""
    assert Vocabulary([" Gauss "]).terms == ("Gauss",)


def test_vocabulary_drops_blank_terms():
    """Empty and whitespace-only terms are dropped."""
    assert Vocabulary(["Gauss", "  ", ""]).terms == ("Gauss",)


def test_vocabulary_drops_duplicate_terms_keeping_first():
    """Exact duplicate terms collapse to their first occurrence, keeping order."""
    assert Vocabulary(["Gauss", "Matris", "Gauss"]).terms == ("Gauss", "Matris")


def test_vocabulary_alpha_defaults_to_one():
    """A Vocabulary built without alpha boosts at strength 1.0."""
    assert Vocabulary(["Gauss"]).alpha == 1.0


@pytest.mark.parametrize("alpha", [0.0, 2.0])
def test_vocabulary_accepts_alpha_at_bounds(alpha: float):
    """Both ends of the 0 to 2 range are valid boost strengths."""
    assert Vocabulary(["Gauss"], alpha).alpha == alpha


@pytest.mark.parametrize("alpha", [-0.1, 2.1, float("nan")])
def test_vocabulary_rejects_alpha_outside_range(alpha: float):
    """A boost strength below 0, above 2, or NaN raises VocabularyError."""
    with pytest.raises(VocabularyError):
        Vocabulary(["Gauss"], alpha)


def test_vocabulary_error_names_alpha():
    """The VocabularyError message names the strength the caller gave."""
    with pytest.raises(VocabularyError, match="2.5"):
        Vocabulary(["Gauss"], 2.5)


# transcribe with a Vocabulary


def test_recognizer_gets_vocabulary_terms_unchanged(source: Path, cache_dir: Path):
    """The recognizer receives the Vocabulary's terms with their capitalisation unchanged."""
    received = []
    transcribe(source, vocabulary=Vocabulary(["SF1624", "Gausselimination"]), cache_dir=cache_dir, recognize=fake(BOOSTED, received))
    assert received[0].terms == ("SF1624", "Gausselimination")


def test_recognizer_gets_vocabulary_alpha(source: Path, cache_dir: Path):
    """The recognizer receives the Vocabulary's boost strength."""
    received = []
    transcribe(source, vocabulary=Vocabulary(["Gauss"], 1.7), cache_dir=cache_dir, recognize=fake(BOOSTED, received))
    assert received[0].alpha == 1.7


def test_recognizer_gets_none_without_vocabulary(source: Path, cache_dir: Path):
    """A fresh run without a Vocabulary passes None to the recognizer."""
    received = []
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN, received))
    assert received == [None]


def test_blank_vocabulary_reaches_recognizer_as_none(source: Path, cache_dir: Path):
    """A Vocabulary whose terms are all blank counts as none, so the recognizer gets None."""
    received = []
    transcribe(source, vocabulary=Vocabulary(["  ", ""]), cache_dir=cache_dir, recognize=fake(PLAIN, received))
    assert received == [None]


def test_vocabulary_reruns_cached_source(source: Path, cache_dir: Path):
    """A call with a Vocabulary runs the recognizer even when the Source is cached."""
    received = []
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN))
    transcribe(source, vocabulary=gauss(), cache_dir=cache_dir, recognize=fake(BOOSTED, received))
    assert received == [gauss()]


def test_vocabulary_run_keeps_transcript_id(source: Path, cache_dir: Path):
    """A boosted rerun of a cached Source returns the same Transcript ID."""
    first = transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN))
    second = transcribe(source, vocabulary=gauss(), cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert second.transcript_id == first.transcript_id


def test_vocabulary_run_reports_not_cached(source: Path, cache_dir: Path):
    """A boosted rerun of a cached Source reports cached=False."""
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN))
    result = transcribe(source, vocabulary=gauss(), cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert result.cached is False


def test_vocabulary_run_replaces_cached_transcript(source: Path, cache_dir: Path):
    """After a boosted rerun, the read-back returns the boosted Transcript's lines."""
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN))
    result = transcribe(source, vocabulary=gauss(), cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == "[0:01] Idag ska vi prata om Gausselimination."


def test_vocabulary_run_reports_vocabulary(source: Path, cache_dir: Path):
    """A boosted run's stats include the Vocabulary it used."""
    result = transcribe(source, vocabulary=gauss(), cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert result.vocabulary == gauss()


def test_plain_run_reports_no_vocabulary(source: Path, cache_dir: Path):
    """A run without a Vocabulary reports vocabulary None."""
    result = transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN))
    assert result.vocabulary is None


def test_call_without_vocabulary_returns_boosted_transcript_without_running_model(source: Path, cache_dir: Path):
    """After a boosted run, a call without a Vocabulary is a cache hit that never runs the recognizer."""
    transcribe(source, vocabulary=gauss(), cache_dir=cache_dir, recognize=fake(BOOSTED))
    result = transcribe(source, cache_dir=cache_dir, recognize=never_called)
    assert result.cached is True


def test_cache_hit_after_vocabulary_run_reports_stored_vocabulary(source: Path, cache_dir: Path):
    """A cache hit on a boosted Transcript reports the Vocabulary it was made with."""
    transcribe(source, vocabulary=Vocabulary(["Gausselimination"], 0.5), cache_dir=cache_dir, recognize=fake(BOOSTED))
    result = transcribe(source, cache_dir=cache_dir, recognize=never_called)
    assert result.vocabulary == Vocabulary(["Gausselimination"], 0.5)


def test_blank_vocabulary_on_cached_source_is_a_cache_hit(source: Path, cache_dir: Path):
    """A Vocabulary with only blank terms on a cached Source returns the cached Transcript without running the recognizer."""
    transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN))
    result = transcribe(source, vocabulary=Vocabulary(["  "]), cache_dir=cache_dir, recognize=never_called)
    assert result.cached is True


def test_failed_vocabulary_run_keeps_previous_transcript(source: Path, cache_dir: Path):
    """A boosted run that finds no speech leaves the previously cached Transcript in place."""
    first = transcribe(source, cache_dir=cache_dir, recognize=fake(PLAIN))
    with pytest.raises(NoSpeechError):
        transcribe(source, vocabulary=gauss(), cache_dir=cache_dir, recognize=fake([]))
    assert get_transcript(first.transcript_id, cache_dir=cache_dir) == "[0:01] Idag ska vi prata om gauss elimination."


def test_youtube_vocabulary_reruns_cached_video(cache_dir: Path):
    """A boosted call on a cached YouTube Source downloads the video again."""
    calls = []
    transcribe(WATCH_URL, cache_dir=cache_dir, recognize=fake(PLAIN), download=fake_download())
    transcribe(WATCH_URL, vocabulary=gauss(), cache_dir=cache_dir, recognize=fake(BOOSTED), download=fake_download(calls))
    assert len(calls) == 1


# MCP transcribe tool


def test_mcp_transcribe_returns_six_result_fields(source: Path, cache_dir: Path):
    """The transcribe tool returns the five original TranscribeResult fields plus vocabulary."""
    server = create_server(cache_dir=cache_dir, recognize=fake(PLAIN))
    result = call(server, "transcribe", {"source": str(source)})
    assert set(result.structured_content) == {
        "transcript_id",
        "duration_s",
        "segment_count",
        "transcription_s",
        "cached",
        "vocabulary",
    }


def test_mcp_transcribe_passes_vocabulary_terms_to_recognizer(source: Path, cache_dir: Path):
    """The transcribe tool's vocabulary terms reach the recognizer unchanged."""
    received = []
    server = create_server(cache_dir=cache_dir, recognize=fake(BOOSTED, received))
    call(server, "transcribe", {"source": str(source), "vocabulary": ["SF1624", "Gausselimination"]})
    assert received[0].terms == ("SF1624", "Gausselimination")


def test_mcp_transcribe_passes_alpha_to_recognizer(source: Path, cache_dir: Path):
    """The transcribe tool's alpha reaches the recognizer as the boost strength."""
    received = []
    server = create_server(cache_dir=cache_dir, recognize=fake(BOOSTED, received))
    call(server, "transcribe", {"source": str(source), "vocabulary": ["Gausselimination"], "alpha": 1.5})
    assert received[0].alpha == 1.5


def test_mcp_transcribe_reports_vocabulary_as_terms_and_alpha(source: Path, cache_dir: Path):
    """The transcribe tool reports the Vocabulary used as an object with terms and alpha."""
    server = create_server(cache_dir=cache_dir, recognize=fake(BOOSTED))
    result = call(server, "transcribe", {"source": str(source), "vocabulary": ["Gausselimination"], "alpha": 1.5})
    assert result.structured_content["vocabulary"] == {"terms": ["Gausselimination"], "alpha": 1.5}


def test_mcp_transcribe_reports_null_vocabulary_without_terms(source: Path, cache_dir: Path):
    """The transcribe tool reports vocabulary null for a run without terms."""
    server = create_server(cache_dir=cache_dir, recognize=fake(PLAIN))
    result = call(server, "transcribe", {"source": str(source)})
    assert result.structured_content["vocabulary"] is None


@pytest.mark.parametrize("arguments", [{"vocabulary": ["Gausselimination"], "alpha": 2.5}, {"alpha": -1.0}])
def test_mcp_alpha_out_of_range_is_tool_error(arguments: dict, source: Path, cache_dir: Path):
    """An alpha outside 0 to 2 comes back as a tool error carrying the VocabularyError message, with or without terms."""
    server = create_server(cache_dir=cache_dir, recognize=fake(BOOSTED))
    result = call(server, "transcribe", {"source": str(source), **arguments})
    assert "outside 0 to 2" in result.content[0].text


def test_mcp_alpha_out_of_range_leaves_cache_unchanged(source: Path, cache_dir: Path):
    """A call rejected for its alpha caches nothing, so the next plain call transcribes fresh."""
    server = create_server(cache_dir=cache_dir, recognize=fake(BOOSTED))
    call(server, "transcribe", {"source": str(source), "vocabulary": ["Gausselimination"], "alpha": 2.5})
    assert call(server, "transcribe", {"source": str(source)}).structured_content["cached"] is False


def test_mcp_get_transcript_returns_boosted_lines(source: Path, cache_dir: Path):
    """After a boosted transcribe call, the read-back tool returns the boosted Transcript's lines."""
    call(create_server(cache_dir=cache_dir, recognize=fake(PLAIN)), "transcribe", {"source": str(source)})
    server = create_server(cache_dir=cache_dir, recognize=fake(BOOSTED))
    transcript_id = call(server, "transcribe", {"source": str(source), "vocabulary": ["Gausselimination"]}).structured_content["transcript_id"]
    result = call(server, "get_transcript", {"transcript_id": transcript_id})
    assert result.content[0].text == "[0:01] Idag ska vi prata om Gausselimination."


def test_mcp_transcribe_description_says_terms_are_case_sensitive(cache_dir: Path):
    """The transcribe tool's description tells the LLM that Vocabulary terms are case sensitive."""
    assert "case sensitive" in transcribe_description(create_server(cache_dir=cache_dir)).lower()


def test_mcp_transcribe_description_suggests_vocabulary_from_first_pass(cache_dir: Path):
    """The transcribe tool's description tells the LLM it can build a Vocabulary from misspellings in a first pass."""
    description = transcribe_description(create_server(cache_dir=cache_dir)).lower()
    assert "first pass" in description and "misspel" in description


# Real model


@pytest.mark.slow
def test_real_model_transcribes_with_vocabulary(cache_dir: Path):
    """Pianissimo transcribes the Alva clip with a boosted term, and the read-back still mentions matriser."""
    result = transcribe(SPEECH, vocabulary=Vocabulary(["matriser"]), cache_dir=cache_dir)
    assert "matris" in get_transcript(result.transcript_id, cache_dir=cache_dir).lower()
