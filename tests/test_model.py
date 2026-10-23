import onnx_asr
import pytest

from munin.core import load_recognizer


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
