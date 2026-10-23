"""Loading Pianissimo and Silero VAD."""

from collections.abc import Callable, Iterable
from pathlib import Path

from munin.core.segments import Fragment

_MODEL_REPO = "KlangAI/pianissimo-sv-onnx"

Recognize = Callable[[Path], Iterable[Fragment]]
"""Takes a 16 kHz mono wav and yields its raw speech fragments in time order."""


def load_recognizer() -> Recognize:
    """Load Pianissimo (int8) and Silero VAD and return a Recognize function.

    Forces ONNX Runtime's CPU provider for both models, per ADR-0003. VAD treats
    500 ms of silence as a break between fragments and keeps onnx-asr's other
    defaults. On first use, onnx-asr downloads the weights into the Hugging Face
    cache. Later calls load them from there.
    """
    import onnx_asr

    providers = ["CPUExecutionProvider"]
    asr = onnx_asr.load_model(_MODEL_REPO, quantization="int8", providers=providers)
    vad = onnx_asr.load_vad("silero", providers=providers)
    pipeline = asr.with_vad(vad, min_silence_duration_ms=500)

    def recognize(wav: Path) -> Iterable[Fragment]:
        for result in pipeline.recognize(str(wav)):
            yield Fragment(result.start, result.end, result.text)

    return recognize
