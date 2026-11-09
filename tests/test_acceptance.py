"""Acceptance tests for #61: transcribe an English lecture with a Vocabulary."""

import asyncio
import shutil
from pathlib import Path

import pytest
from mcp import Client

from munin.core import (
    Fragment,
    NoSpeechError,
    Video,
    Vocabulary,
    get_transcript,
    load_recognizer,
    transcribe,
)
from munin.mcp_server import create_server

FIXTURES = Path(__file__).parent / "fixtures"
SPEECH = FIXTURES / "sv_short.m4a"
SPEECH_EN = FIXTURES / "en_short.m4a"
WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

TERMS = Vocabulary(["fork()", "PCB"], 1.5)
PLAIN = Fragment(1.2, 3.0, "The parent calls fork and gets a PCB.")
BOOSTED = Fragment(1.2, 3.0, "The parent calls fork() and gets a PCB.")
PLAIN_LINE = "[0:01] The parent calls fork and gets a PCB."
BOOSTED_LINE = "[0:01] The parent calls fork() and gets a PCB."


def fake(*fragments: Fragment, received: list | None = None):
    """A recognizer that ignores the audio, records each Vocabulary it gets in `received`, and yields the given fragments."""

    def recognize(wav: Path, vocabulary: Vocabulary | None):
        if received is not None:
            received.append(vocabulary)
        return list(fragments)

    return recognize


def never_called(wav: Path, vocabulary: Vocabulary | None):
    raise AssertionError("the recognizer ran on what should be a cache hit")


def fake_download(video: Video, workdir: Path) -> Path:
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""
    audio = workdir / "audio.m4a"
    shutil.copy(SPEECH, audio)
    return audio


@pytest.fixture
def cached_english(source: Path, cache_dir: Path) -> str:
    """An unboosted English Transcript of `source` in the cache, returning its Transcript ID."""
    return transcribe(source, language="en", cache_dir=cache_dir, recognize=fake(PLAIN)).transcript_id


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def tool_description(server, name: str) -> str:
    """Return a tool's description with every run of whitespace collapsed to one space."""

    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    description = next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)
    return " ".join(description.split())


# Rerunning a cached English Transcript with terms


def test_english_terms_rerun_a_cached_english_source(source: Path, cache_dir: Path, cached_english: str):
    """An `en` call with terms on a cached English Transcript runs the recognizer with those terms."""
    received = []
    transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED, received=received))
    assert received == [TERMS]


def test_english_terms_run_keeps_the_transcript_id(source: Path, cache_dir: Path, cached_english: str):
    """A boosted English rerun keeps the cached Transcript's ID."""
    result = transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert result.transcript_id == cached_english


def test_english_terms_run_reports_not_cached(source: Path, cache_dir: Path, cached_english: str):
    """A boosted English rerun reports cached=False, since the model ran."""
    result = transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert result.cached is False


def test_english_terms_run_reports_english(source: Path, cache_dir: Path, cached_english: str):
    """A boosted English rerun reports `en` as its language."""
    result = transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert result.language == "en"


def test_english_terms_run_reports_the_vocabulary(source: Path, cache_dir: Path, cached_english: str):
    """A boosted English rerun reports the Vocabulary it used."""
    result = transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert result.vocabulary == TERMS


def test_english_terms_run_replaces_the_cached_lines(source: Path, cache_dir: Path, cached_english: str):
    """After a boosted English rerun, `get_transcript` returns the boosted lines under the old ID."""
    transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert get_transcript(cached_english, cache_dir=cache_dir) == BOOSTED_LINE


def test_english_terms_run_stores_english(source: Path, cache_dir: Path, cached_english: str):
    """A boosted English rerun stores `en`, so a later plain call reports English."""
    transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).language == "en"


def test_english_terms_run_stores_the_vocabulary(source: Path, cache_dir: Path, cached_english: str):
    """A boosted English rerun stores its Vocabulary, so a later plain call reports it."""
    transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).vocabulary == TERMS


def test_later_plain_call_returns_the_boosted_english_transcript_without_a_run(
    source: Path, cache_dir: Path, cached_english: str
):
    """A call with no Vocabulary after a boosted English run is a cache hit and runs no model."""
    transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert transcribe(source, language="en", cache_dir=cache_dir, recognize=never_called).cached is True


# English terms with nothing cached


def test_english_terms_on_a_miss_reach_the_recognizer(source: Path, cache_dir: Path):
    """An `en` call with terms and nothing cached runs the recognizer with those terms."""
    received = []
    transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED, received=received))
    assert received == [TERMS]


def test_english_terms_on_a_miss_report_english(source: Path, cache_dir: Path):
    """An `en` call with terms and nothing cached reports `en`."""
    result = transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert result.language == "en"


def test_english_terms_on_a_youtube_source_reach_the_recognizer(cache_dir: Path):
    """An `en` call with terms on a YouTube Source downloads it and runs the recognizer with those terms."""
    received = []
    recognize = fake(BOOSTED, received=received)
    transcribe(WATCH_URL, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=recognize, download=fake_download)
    assert received == [TERMS]


# Terms with no language on a cached English Transcript


def test_no_language_terms_on_cached_english_reach_the_recognizer(source: Path, cache_dir: Path, cached_english: str):
    """Terms with no language on a cached English Transcript rerun it with those terms."""
    received = []
    transcribe(source, vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED, received=received))
    assert received == [TERMS]


def test_no_language_terms_on_cached_english_stay_english(source: Path, cache_dir: Path, cached_english: str):
    """Terms with no language on a cached English Transcript rerun in English, not Swedish."""
    result = transcribe(source, vocabulary=TERMS, cache_dir=cache_dir, recognize=fake(BOOSTED))
    assert result.language == "en"


# A failed boosted English run


def test_failed_boosted_english_run_keeps_the_previous_lines(source: Path, cache_dir: Path, cached_english: str):
    """A boosted English run that finds no speech leaves the previous cached Transcript's lines in place."""
    with pytest.raises(NoSpeechError):
        transcribe(source, language="en", vocabulary=TERMS, cache_dir=cache_dir, recognize=fake())
    assert get_transcript(cached_english, cache_dir=cache_dir) == PLAIN_LINE


# MCP tool


def test_mcp_transcribe_english_with_terms_reports_the_vocabulary(source: Path, cache_dir: Path):
    """The transcribe tool's `en` call with terms reports the terms and alpha it used."""
    server = create_server(cache_dir=cache_dir, recognize=fake(BOOSTED))
    result = call(server, "transcribe", {"source": str(source), "language": "en", "vocabulary": ["PCB"], "alpha": 1.5})
    assert result.structured_content["vocabulary"] == {"terms": ["PCB"], "alpha": 1.5}


def test_mcp_transcribe_description_says_vocabulary_works_in_both_languages(cache_dir: Path):
    """The transcribe tool's description tells the LLM a Vocabulary works on Swedish and English lectures alike."""
    assert "both languages" in tool_description(create_server(cache_dir=cache_dir), "transcribe").lower()


def test_mcp_transcribe_description_says_boosting_fixes_what_the_model_heard(cache_dir: Path):
    """The transcribe tool's description tells the LLM boosting fixes the spelling of a sound the model heard."""
    assert "heard" in tool_description(create_server(cache_dir=cache_dir), "transcribe").lower()


def test_mcp_transcribe_description_says_boosting_makes_no_identifiers(cache_dir: Path):
    """The transcribe tool's description tells the LLM boosting does not turn two spoken words into one identifier."""
    assert "identifier" in tool_description(create_server(cache_dir=cache_dir), "transcribe").lower()


# Real model


@pytest.mark.slow
def test_real_english_model_spells_a_boosted_term(cache_dir: Path):
    """Parakeet spells the English clip's "process" as "processor" when that term is boosted at full strength, which it never writes unboosted."""
    result = transcribe(SPEECH_EN, language="en", vocabulary=Vocabulary(["processor"], 2.0), cache_dir=cache_dir)
    assert "processor" in get_transcript(result.transcript_id, cache_dir=cache_dir)


@pytest.mark.slow
def test_real_english_recognizer_call_without_vocabulary_drops_the_previous_boost(tmp_path: Path):
    """An English recognizer called with None after a boosted call runs unboosted, so "processor" turns back into "process"."""
    recognize = load_recognizer("en")
    boosted_dir, plain_dir = tmp_path / "boosted", tmp_path / "plain"
    transcribe(SPEECH_EN, language="en", vocabulary=Vocabulary(["processor"], 2.0), cache_dir=boosted_dir, recognize=recognize)
    plain = transcribe(SPEECH_EN, language="en", cache_dir=plain_dir, recognize=recognize)
    assert "processor" not in get_transcript(plain.transcript_id, cache_dir=plain_dir)
