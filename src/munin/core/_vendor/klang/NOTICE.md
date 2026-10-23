# Klang phrase boosting

Vendored from https://huggingface.co/KlangAI/pianissimo-sv-onnx at revision
`63730c6021234f26b9bbae9a07a04fec39e7a52e` (ADR-0008).

Files: `pianissimo_onnx.py`, `phrase_boost.py`, `tokenizer.model`.
Licence: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/
Author: Klang. `phrase_boost.py` is a numpy port of NeMo's GPU-PB boosting tree (Apache 2.0).

Changed from upstream: `pianissimo_onnx.py` imports `phrase_boost` relatively.
Re-vendor from a new revision, and review the diff, before changing this pin.
