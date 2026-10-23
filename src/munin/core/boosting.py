"""Applying a Vocabulary to a loaded onnx-asr model, through Klang's vendored phrase boosting."""

from munin.core._vendor.klang import pianissimo_onnx
from munin.core.vocabulary import Vocabulary


def apply_vocabulary(model, vocabulary: Vocabulary | None) -> None:
    """Boost `model` with `vocabulary`, or switch boosting off when it is None.

    Boosting patches the loaded model in place, so every call replaces whatever
    the previous call set, per ADR-0009.
    """
    if vocabulary is None:
        pianissimo_onnx.boost(model, [])
    else:
        pianissimo_onnx.boost(model, list(vocabulary.terms), alpha=vocabulary.alpha)
