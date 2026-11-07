import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import onnx_asr
import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from munin.core import (
    EnglishVocabularyError,
    Fragment,
    LanguageError,
    NoSpeechError,
    SourceError,
    Video,
    Vocabulary,
    get_transcript,
    load_recognizer,
    parse_language,
    read_slides,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

FIXTURES = Path(__file__).parent / "fixtures"
SPEECH = FIXTURES / "sv_short.m4a"
SPEECH_EN = FIXTURES / "en_short.m4a"

PIANISSIMO = "KlangAI/pianissimo-sv-onnx"
PARAKEET = "istupakov/parakeet-tdt-0.6b-v3-onnx"

WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
KTHPLAY_URL = "https://play.kth.se/media/t/0_1zk8obn5"
DECK_PATH = "/tmp/matriser.pdf"

BAD_LANGUAGES = ["de", "", "EN", "english", "sv "]

GAUSS = Vocabulary(["Gausselimination"])
SWEDISH_LINE = "[0:01] Idag ska vi prata om matriser."
ENGLISH_LINE = "[0:01] Today we talk about processes."


def fake(text: str = "Idag ska vi prata om matriser.", received: list | None = None):
    """A recognizer that ignores the audio, records each Vocabulary it gets in `received`, and yields one sentence."""

    def recognize(wav: Path, vocabulary: Vocabulary | None):
        if received is not None:
            received.append(vocabulary)
        return [Fragment(1.2, 3.0, text)]

    return recognize


SWEDISH = fake()
ENGLISH = fake("Today we talk about processes.")


def no_speech(wav: Path, vocabulary: Vocabulary | None):
    return []


def never_called(wav: Path, vocabulary: Vocabulary | None):
    raise AssertionError("the recognizer ran on a call that should not run it")


def fake_download(calls: list | None = None):
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""

    def download(video: Video, workdir: Path) -> Path:
        if calls is not None:
            calls.append(video)
        audio = workdir / "audio.m4a"
        shutil.copy(SPEECH, audio)
        return audio

    return download


def never_download(video: Video, workdir: Path) -> Path:
    raise AssertionError("the downloader ran on a call that should not download")


def unfetchable(video: Video, workdir: Path) -> Path:
    raise SourceError(video.url, "Video unavailable")


@pytest.fixture
def speech_library(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Fakes onnx-asr, the outside library, and records what each load asked for."""
    library = SimpleNamespace(repos=[], model_arguments=[], vad_arguments=[], silence_breaks=[])

    class FakeAsr:
        asr = SimpleNamespace()

        def with_vad(self, vad, **kwargs):
            library.silence_breaks.append(kwargs.get("min_silence_duration_ms"))
            return self

        def recognize(self, path):
            return [SimpleNamespace(start=1.2, end=3.0, text="Hello there.")]

    def load_model(repo, *args, **kwargs):
        library.repos.append(repo)
        library.model_arguments.append(kwargs)
        return FakeAsr()

    def load_vad(name, *args, **kwargs):
        library.vad_arguments.append(kwargs)
        return object()

    monkeypatch.setattr(onnx_asr, "load_model", load_model)
    monkeypatch.setattr(onnx_asr, "load_vad", load_vad)
    return library


def write_entry_from_before_languages(source: Path, cache_dir: Path) -> str:
    """Write a cache file for `source` as Munin wrote it before languages existed, and return its Transcript ID."""
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


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def list_tools(server):
    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    return asyncio.run(run()).tools


def tool_description(server, name: str) -> str:
    """Return a tool's description with every run of whitespace collapsed to one space, so phrases match across line wraps."""
    description = next(tool.description for tool in list_tools(server) if tool.name == name)
    return " ".join(description.split())


def prompt_text(server, **arguments) -> str:
    async def run():
        async with Client(server) as client:
            return await client.get_prompt("lecture_to_mindmap", arguments)

    return asyncio.run(run()).messages[0].content.text


def prompt_error(server, **arguments) -> MCPError | None:
    """Return the MCP error that getting the prompt raises, or None when it succeeds."""

    async def run():
        async with Client(server) as client:
            try:
                await client.get_prompt("lecture_to_mindmap", arguments)
            except MCPError as error:
                return error
            return None

    return asyncio.run(run())


# parse_language


@pytest.mark.parametrize("language", ["sv", "en"])
def test_parse_language_returns_a_known_language(language: str):
    """`sv` and `en` come back as themselves."""
    assert parse_language(language) == language


def test_parse_language_returns_none_for_no_language():
    """None means the caller gave no language."""
    assert parse_language(None) is None


@pytest.mark.parametrize("language", BAD_LANGUAGES)
def test_parse_language_rejects_anything_else(language: str):
    """Anything but an exact `sv` or `en` raises LanguageError."""
    with pytest.raises(LanguageError):
        parse_language(language)


def test_language_error_names_the_value():
    """The error says which value was wrong and which values are right."""
    with pytest.raises(LanguageError, match="Language de is not sv or en"):
        parse_language("de")


# The recognizer for each language


def test_english_recognizer_loads_parakeet(speech_library: SimpleNamespace):
    """`load_recognizer("en")` loads Parakeet and no other speech model."""
    load_recognizer("en")
    assert speech_library.repos == [PARAKEET]


def test_english_recognizer_loads_int8_weights(speech_library: SimpleNamespace):
    """Parakeet loads as int8."""
    load_recognizer("en")
    assert speech_library.model_arguments[0]["quantization"] == "int8"


def test_english_recognizer_forces_cpu_provider_for_model(speech_library: SimpleNamespace):
    """Parakeet loads with only ONNX Runtime's CPU provider."""
    load_recognizer("en")
    assert speech_library.model_arguments[0]["providers"] == ["CPUExecutionProvider"]


def test_english_recognizer_forces_cpu_provider_for_vad(speech_library: SimpleNamespace):
    """Silero VAD loads with only ONNX Runtime's CPU provider on an English run too."""
    load_recognizer("en")
    assert speech_library.vad_arguments[0]["providers"] == ["CPUExecutionProvider"]


def test_english_recognizer_breaks_fragments_at_500_ms_of_silence(speech_library: SimpleNamespace):
    """VAD treats 500 ms of silence as a break on English, as on Swedish."""
    load_recognizer("en")
    assert speech_library.silence_breaks == [500]


def test_load_recognizer_rejects_an_unknown_language_before_loading(speech_library: SimpleNamespace):
    """An unknown language raises LanguageError, and neither model starts loading."""
    with pytest.raises(LanguageError):
        load_recognizer("de")
    assert speech_library.repos == []


# A run loads only the model its language needs


def test_english_call_on_a_miss_loads_only_parakeet(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A call with `en` and nothing cached loads Parakeet and never Pianissimo."""
    transcribe(source, language="en", cache_dir=cache_dir)
    assert speech_library.repos == [PARAKEET]


def test_swedish_call_on_a_miss_loads_only_pianissimo(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A call with `sv` and nothing cached loads Pianissimo and never Parakeet."""
    transcribe(source, language="sv", cache_dir=cache_dir)
    assert speech_library.repos == [PIANISSIMO]


def test_call_with_no_language_on_a_miss_runs_swedish(source: Path, cache_dir: Path, speech_library: SimpleNamespace):
    """A call with no language and nothing cached loads Pianissimo and reports `sv`."""
    result = transcribe(source, cache_dir=cache_dir)
    assert (speech_library.repos, result.language) == ([PIANISSIMO], "sv")


# A fresh English run


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

    def recognize(wav: Path, vocabulary: Vocabulary | None):
        return [Fragment(0.0, 1.0, "The first part is"), Fragment(1.2, 2.0, "the size.")]

    assert transcribe(source, language="en", cache_dir=cache_dir, recognize=recognize).segment_count == 1


def test_english_run_from_youtube_reports_english(cache_dir: Path):
    """A YouTube Source runs in English too."""
    result = transcribe(WATCH_URL, language="en", cache_dir=cache_dir, recognize=ENGLISH, download=fake_download())
    assert result.language == "en"


def test_english_run_from_kthplay_reports_english(cache_dir: Path):
    """A KTH Play Source runs in English too."""
    result = transcribe(KTHPLAY_URL, language="en", cache_dir=cache_dir, recognize=ENGLISH, download=fake_download())
    assert result.language == "en"


# A later call with no language


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


# A later call with the same language


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


# A later call with a different language


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


# A Transcript cached before this change


def test_old_transcript_counts_as_swedish(source: Path, cache_dir: Path):
    """A cache file with no language reports `sv`."""
    write_entry_from_before_languages(source, cache_dir)
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).language == "sv"


def test_old_transcript_is_a_cache_hit_for_swedish(source: Path, cache_dir: Path):
    """A `sv` call on a cache file with no language reports cached=True."""
    write_entry_from_before_languages(source, cache_dir)
    assert transcribe(source, language="sv", cache_dir=cache_dir, recognize=never_called).cached is True


def test_old_transcript_is_replaced_by_english(source: Path, cache_dir: Path):
    """An `en` call on a cache file with no language runs English under the same ID."""
    transcript_id = write_entry_from_before_languages(source, cache_dir)
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    assert get_transcript(transcript_id, cache_dir=cache_dir) == ENGLISH_LINE


def test_old_transcript_with_vocabulary_reruns_swedish(source: Path, cache_dir: Path):
    """Terms and no language on a cache file with no language rerun Swedish and report `sv`."""
    write_entry_from_before_languages(source, cache_dir)
    assert transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=SWEDISH).language == "sv"


# A bad language


@pytest.mark.parametrize("language", BAD_LANGUAGES)
def test_bad_language_raises_language_error(language: str, source: Path, cache_dir: Path):
    """Anything but an exact `sv` or `en` raises LanguageError."""
    with pytest.raises(LanguageError):
        transcribe(source, language=language, cache_dir=cache_dir, recognize=never_called)


def test_bad_language_fails_before_download_or_model(cache_dir: Path, speech_library: SimpleNamespace):
    """A bad language on a video raises LanguageError with neither the downloader nor the model touched."""
    with pytest.raises(LanguageError):
        transcribe(WATCH_URL, language="de", cache_dir=cache_dir, download=never_download)


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


# Vocabulary on an English lecture


def test_english_with_terms_raises(source: Path, cache_dir: Path):
    """Terms with `en` raise EnglishVocabularyError."""
    with pytest.raises(EnglishVocabularyError):
        transcribe(source, language="en", vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called)


def test_english_vocabulary_error_says_what_to_do(source: Path, cache_dir: Path):
    """The error tells the caller to call again without terms."""
    with pytest.raises(EnglishVocabularyError, match="Call again without them"):
        transcribe(source, language="en", vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called)


def test_english_with_terms_fails_before_download(cache_dir: Path):
    """Terms with `en` on a video raise without touching the downloader."""
    with pytest.raises(EnglishVocabularyError):
        transcribe(WATCH_URL, language="en", vocabulary=GAUSS, cache_dir=cache_dir, recognize=never_called, download=never_download)


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


def test_blank_vocabulary_on_english_counts_as_none(source: Path, cache_dir: Path):
    """A Vocabulary whose terms are all blank is no Vocabulary, so an `en` run goes ahead with None."""
    received: list = []
    transcribe(source, language="en", vocabulary=Vocabulary(["  "]), cache_dir=cache_dir, recognize=fake(received=received))
    assert received == [None]


# Vocabulary on a Swedish lecture


def test_swedish_terms_reach_the_recognizer(source: Path, cache_dir: Path):
    """Terms with `sv` reach the recognizer unchanged."""
    received: list = []
    transcribe(source, language="sv", vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(received=received))
    assert received == [GAUSS]


def test_swedish_terms_rerun_a_cached_swedish_transcript(source: Path, cache_dir: Path):
    """Terms with `sv` on a cached Swedish Transcript run again, as they do today."""
    received: list = []
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    transcribe(source, language="sv", vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(received=received))
    assert received == [GAUSS]


def test_swedish_terms_replace_a_cached_english_transcript(source: Path, cache_dir: Path):
    """Terms with `sv` on a cached English Transcript run Swedish with those terms."""
    received: list = []
    transcribe(source, language="en", cache_dir=cache_dir, recognize=ENGLISH)
    transcribe(source, language="sv", vocabulary=GAUSS, cache_dir=cache_dir, recognize=fake(received=received))
    assert received == [GAUSS]


def test_terms_with_no_language_on_a_miss_run_swedish(source: Path, cache_dir: Path):
    """Terms with no language and nothing cached run Swedish and report `sv`."""
    assert transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=SWEDISH).language == "sv"


def test_terms_with_no_language_on_cached_swedish_stay_swedish(source: Path, cache_dir: Path):
    """Terms with no language on a cached Swedish Transcript rerun it and report `sv`."""
    transcribe(source, cache_dir=cache_dir, recognize=SWEDISH)
    assert transcribe(source, vocabulary=GAUSS, cache_dir=cache_dir, recognize=SWEDISH).language == "sv"


# A failed run


def test_failed_english_run_leaves_swedish_text(source: Path, cache_dir: Path):
    """An `en` run that finds no speech leaves the Swedish Transcript's text in place."""
    result = transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    with pytest.raises(NoSpeechError):
        transcribe(source, language="en", cache_dir=cache_dir, recognize=no_speech)
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == SWEDISH_LINE


def test_failed_english_run_leaves_swedish_language(source: Path, cache_dir: Path):
    """An `en` run that finds no speech leaves the stored language at `sv`."""
    transcribe(source, language="sv", cache_dir=cache_dir, recognize=SWEDISH)
    with pytest.raises(NoSpeechError):
        transcribe(source, language="en", cache_dir=cache_dir, recognize=no_speech)
    assert transcribe(source, cache_dir=cache_dir, recognize=never_called).language == "sv"


def test_failed_download_leaves_the_cached_transcript(cache_dir: Path):
    """An `en` run whose download fails leaves the Swedish Transcript's text in place."""
    result = transcribe(WATCH_URL, language="sv", cache_dir=cache_dir, recognize=SWEDISH, download=fake_download())
    with pytest.raises(SourceError):
        transcribe(WATCH_URL, language="en", cache_dir=cache_dir, recognize=ENGLISH, download=unfetchable)
    assert get_transcript(result.transcript_id, cache_dir=cache_dir) == SWEDISH_LINE


def test_failed_first_english_run_is_not_cached(source: Path, cache_dir: Path):
    """An `en` run that finds no speech caches nothing, so the next plain call transcribes fresh."""
    with pytest.raises(NoSpeechError):
        transcribe(source, language="en", cache_dir=cache_dir, recognize=no_speech)
    assert transcribe(source, cache_dir=cache_dir, recognize=SWEDISH).cached is False


# The transcribe tool


def test_tool_reports_english(source: Path, cache_dir: Path):
    """The tool's `en` call returns `language` as `en`."""
    server = create_server(cache_dir=cache_dir, recognize=ENGLISH)
    result = call(server, "transcribe", {"source": str(source), "language": "en"})
    assert result.structured_content["language"] == "en"


def test_tool_with_no_language_reports_swedish(source: Path, cache_dir: Path):
    """The tool's call with no language and nothing cached returns `language` as `sv`."""
    server = create_server(cache_dir=cache_dir, recognize=SWEDISH)
    result = call(server, "transcribe", {"source": str(source)})
    assert result.structured_content["language"] == "sv"


def test_tool_with_no_language_returns_cached_english(source: Path, cache_dir: Path):
    """After an English run, the tool's call with no language returns `language` as `en`."""
    server = create_server(cache_dir=cache_dir, recognize=ENGLISH)
    call(server, "transcribe", {"source": str(source), "language": "en"})
    assert call(server, "transcribe", {"source": str(source)}).structured_content["language"] == "en"


def test_tool_english_without_terms_reports_no_vocabulary(source: Path, cache_dir: Path):
    """The tool builds an empty Vocabulary on every call, and that does not trip the English check."""
    server = create_server(cache_dir=cache_dir, recognize=ENGLISH)
    result = call(server, "transcribe", {"source": str(source), "language": "en"})
    assert result.structured_content["vocabulary"] is None


def test_tool_english_with_terms_is_a_tool_error_saying_so(source: Path, cache_dir: Path):
    """The tool's `en` call with terms comes back as a tool error carrying the core's message."""
    server = create_server(cache_dir=cache_dir, recognize=ENGLISH)
    result = call(server, "transcribe", {"source": str(source), "language": "en", "vocabulary": ["heap"]})
    assert "do not work on English lectures" in result.content[0].text


def test_tool_schema_lists_the_two_languages(cache_dir: Path):
    """The tool's schema shows the LLM `sv` and `en` as the only language values."""
    transcribe_tool = next(tool for tool in list_tools(create_server(cache_dir=cache_dir)) if tool.name == "transcribe")
    choices = transcribe_tool.input_schema["properties"]["language"]["anyOf"]
    assert {"enum": ["sv", "en"], "type": "string"} in choices


def test_tool_rejects_a_bad_language_naming_both(source: Path, cache_dir: Path):
    """The tool's call with a bad language is an error that names `sv` and `en`."""
    server = create_server(cache_dir=cache_dir, recognize=never_called)
    result = call(server, "transcribe", {"source": str(source), "language": "de"})
    assert result.is_error and "'sv'" in result.content[0].text and "'en'" in result.content[0].text


def test_tool_description_names_the_languages(cache_dir: Path):
    """The tool's description tells the LLM what `language` takes."""
    description = tool_description(create_server(cache_dir=cache_dir), "transcribe")
    assert "`language`" in description and "`sv`" in description and "`en`" in description


def test_tool_description_says_a_miss_defaults_to_swedish(cache_dir: Path):
    """The tool's description warns the LLM that a call with no language and nothing cached runs Swedish."""
    assert "swedish" in tool_description(create_server(cache_dir=cache_dir), "transcribe").lower()


def test_tool_description_says_english_has_no_vocabulary_yet(cache_dir: Path):
    """The tool's description tells the LLM that Vocabulary terms do not work on English lectures yet."""
    assert "english lectures" in tool_description(create_server(cache_dir=cache_dir), "transcribe").lower()


# The lecture_to_mindmap prompt


@pytest.mark.parametrize("language", ["sv", "en"])
def test_prompt_asks_transcribe_for_the_language(language: str, cache_dir: Path):
    """With a Source and a language, the `transcribe` step names the language."""
    text = prompt_text(create_server(cache_dir=cache_dir), source=WATCH_URL, language=language)
    assert f"Call `transcribe` with that Source and language `{language}`." in text


def test_prompt_with_deck_and_language_still_reads_slides(cache_dir: Path):
    """A language does not drop the `read_slides` step when a Deck is given too."""
    text = prompt_text(create_server(cache_dir=cache_dir), source=WATCH_URL, deck=DECK_PATH, language="en")
    assert "Call `read_slides`" in text


def test_prompt_with_empty_language_matches_no_language(cache_dir: Path):
    """An empty language counts as none, so the text is the same as with no language."""
    server = create_server(cache_dir=cache_dir)
    assert prompt_text(server, source=WATCH_URL, language="") == prompt_text(server, source=WATCH_URL)


def test_prompt_with_empty_language_and_only_a_deck_matches_no_language(cache_dir: Path):
    """An empty language on a Deck alone counts as none, so it stays the slides-only text."""
    server = create_server(cache_dir=cache_dir)
    assert prompt_text(server, deck=DECK_PATH, language="") == prompt_text(server, deck=DECK_PATH)


def test_prompt_rejects_a_bad_language(cache_dir: Path):
    """A bad language fails with an MCP error carrying the LanguageError message."""
    error = prompt_error(create_server(cache_dir=cache_dir), source=WATCH_URL, language="de")
    assert "Language de is not sv or en" in str(error)


def test_prompt_rejects_a_language_with_only_a_deck(cache_dir: Path):
    """A language with no Source fails, since a Deck alone never transcribes."""
    error = prompt_error(create_server(cache_dir=cache_dir), deck=DECK_PATH, language="en")
    assert "A language needs a Source" in str(error)


def test_prompt_with_only_a_language_asks_for_a_source_or_deck(cache_dir: Path):
    """A language with neither a Source nor a Deck gets the error for having neither."""
    error = prompt_error(create_server(cache_dir=cache_dir), language="en")
    assert "Give a Source, a Deck, or both" in str(error)


# Real model


@pytest.mark.slow
def test_real_english_model_transcribes_english_speech(cache_dir: Path):
    """Parakeet transcribes the English clip, and the read-back mentions a process."""
    result = transcribe(SPEECH_EN, language="en", cache_dir=cache_dir)
    assert "process" in get_transcript(result.transcript_id, cache_dir=cache_dir).lower()
