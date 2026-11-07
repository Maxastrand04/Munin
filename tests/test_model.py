from pathlib import Path
from types import SimpleNamespace

import onnx_asr
import pytest

from munin.core import (
    LanguageError,
    Vocabulary,
    get_transcript,
    load_recognizer,
    transcribe,
)

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
PARAKEET = "istupakov/parakeet-tdt-0.6b-v3-onnx"


@pytest.fixture
def loaded_providers(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Fakes onnx-asr's loaders and records the providers each one was given."""
    providers = {}

    class FakeAsr:
        def with_vad(self, vad, **kwargs):
            return self

    def load_model(repo, **kwargs):
        providers["model"] = kwargs.get("providers")
        return FakeAsr()

    def load_vad(name, **kwargs):
        providers["vad"] = kwargs.get("providers")
        return object()

    monkeypatch.setattr(onnx_asr, "load_model", load_model)
    monkeypatch.setattr(onnx_asr, "load_vad", load_vad)
    load_recognizer()
    return providers


def test_loader_forces_cpu_provider_for_model(loaded_providers: dict):
    """Pianissimo loads with only ONNX Runtime's CPU provider."""
    assert loaded_providers["model"] == ["CPUExecutionProvider"]


def test_loader_forces_cpu_provider_for_vad(loaded_providers: dict):
    """Silero VAD loads with only ONNX Runtime's CPU provider."""
    assert loaded_providers["vad"] == ["CPUExecutionProvider"]


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


def test_unknown_language_raises_language_error(speech_library: SimpleNamespace):
    """An unknown language raises LanguageError."""
    with pytest.raises(LanguageError):
        load_recognizer("de")


def test_unknown_language_loads_no_model(speech_library: SimpleNamespace):
    """An unknown language fails before either model starts loading."""
    with pytest.raises(LanguageError):
        load_recognizer("de")
    assert speech_library.repos == []


@pytest.mark.slow
def test_recognizer_call_without_vocabulary_drops_the_previous_boost(tmp_path: Path):
    """A recognizer called with None after a boosted call runs unboosted, so "matrix" turns back into "matris"."""
    recognize = load_recognizer()
    transcribe(SPEECH, vocabulary=Vocabulary(["matrix"], 2.0), cache_dir=tmp_path / "boosted", recognize=recognize)
    plain = transcribe(SPEECH, cache_dir=tmp_path / "plain", recognize=recognize)
    assert "matrix" not in get_transcript(plain.transcript_id, cache_dir=tmp_path / "plain")
