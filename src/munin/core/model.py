"""Loading a language's speech model and Silero VAD."""

from collections.abc import Callable, Iterable
from pathlib import Path

from munin.core.boosting import apply_vocabulary
from munin.core.errors import LanguageError
from munin.core.language import Language
from munin.core.segments import Fragment
from munin.core.vocabulary import Vocabulary

_MODEL_REPOS: dict[Language, str] = {
    "sv": "KlangAI/pianissimo-sv-onnx",
    "en": "istupakov/parakeet-tdt-0.6b-v3-onnx",
}

Recognize = Callable[[Path, Vocabulary | None], Iterable[Fragment]]
"""Takes a 16 kHz mono wav and a Vocabulary or None, and yields the wav's raw speech fragments in time order.

The Vocabulary's terms are boosted at its `alpha`, with their capitalisation
unchanged. `None` means no boosting. Each call applies only the Vocabulary it
was given, so a call with `None` after a boosted call runs unboosted. See
ADR-0009.
"""


def load_recognizer(language: Language = "sv") -> Recognize:
    """Load `language`'s speech model (int8) and Silero VAD and return a Recognize function.

    `sv` loads Pianissimo from `KlangAI/pianissimo-sv-onnx`. `en` loads Parakeet
    TDT 0.6B v3 from `istupakov/parakeet-tdt-0.6b-v3-onnx`, per ADR-0022. A call
    loads only the one model its language needs. Each follows its repo's main
    branch.

    Forces ONNX Runtime's CPU provider for both models, per ADR-0003. VAD treats
    500 ms of silence as a break between fragments and keeps onnx-asr's other
    defaults. On first use, onnx-asr downloads the weights into the Hugging Face
    cache. Later calls load them from there. Boosting goes through Klang's
    vendored phrase boosting, per ADR-0008, and only the `sv` recognizer boosts.
    The `en` recognizer ignores the Vocabulary it is given, per ADR-0023.

    Raises `LanguageError` when `language` is not `sv` or `en`, before anything
    loads.
    """
    if language not in _MODEL_REPOS:
        raise LanguageError(language)
    import onnx_asr

    providers = ["CPUExecutionProvider"]
    asr = onnx_asr.load_model(_MODEL_REPOS[language], quantization="int8", providers=providers)
    vad = onnx_asr.load_vad("silero", providers=providers)
    pipeline = asr.with_vad(vad, min_silence_duration_ms=500)

    def recognize(wav: Path, vocabulary: Vocabulary | None) -> Iterable[Fragment]:
        if language == "sv":
            apply_vocabulary(asr, vocabulary)
        for result in pipeline.recognize(str(wav)):
            yield Fragment(result.start, result.end, result.text)

    return recognize
