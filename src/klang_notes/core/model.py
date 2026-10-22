"""Loading Pianissimo and Silero VAD."""

from collections.abc import Callable, Iterable
from pathlib import Path

from klang_notes.core.segments import Fragment

Recognize = Callable[[Path], Iterable[Fragment]]
"""Takes a 16 kHz mono wav and yields its raw speech fragments in time order."""


def load_recognizer() -> Recognize:
    """Load Pianissimo (int8) and Silero VAD and return a Recognize function.

    Forces ONNX Runtime's CPU provider for both models, per ADR-0003. VAD treats
    500 ms of silence as a break between fragments and keeps onnx-asr's other
    defaults. On first use, onnx-asr downloads the weights into the Hugging Face
    cache. Later calls load them from there.
    """
    raise NotImplementedError
