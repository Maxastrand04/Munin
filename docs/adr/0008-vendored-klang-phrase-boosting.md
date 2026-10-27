# ADR-0008: Phrase boosting runs Klang's vendored code through one module

**Decision:** Klang's phrase boosting code, `pianissimo_onnx.py`, `phrase_boost.py` and `tokenizer.model`, MUST be vendored at a pinned revision of `KlangAI/pianissimo-sv-onnx` under `src/munin/core/_vendor/klang/` with its CC BY 4.0 attribution, MUST be imported only by `src/munin/core/boosting.py`, and MUST NOT be downloaded at runtime.

**Reason:** onnx-asr has no phrase boosting, and Klang ships it as loose files on Hugging Face, not as a package. Their README fetches the files with `huggingface_hub.snapshot_download` at runtime and imports them. That lost for three reasons. A module fetching with the hub and calling Klang's helper wraps two dependencies, which PCR-0004 forbids. The program would run code downloaded from the internet. And a change Klang makes upstream would reach users without anyone reviewing it. Vendoring costs about 6 KB of code and a 360 KB tokenizer, and turns each upstream change into a reviewed diff.

**Consequence:** `boosting.py` is the one module that imports the vendored helper. `model.py` hands it the loaded onnx-asr model and never imports the helper itself. `sentencepiece` is a project dependency because the helper needs it. The helper replaces a private onnx-asr method, `_decoding`, so `onnx-asr` stays pinned below 0.13, and raising that pin means re-vendoring from Klang or checking that boosting still decodes. Lint skips `_vendor/`, so the vendored files stay as Klang ships them and a re-vendor never turns the lint check red. A `snapshot_download` of `*.py` files, a lint fix inside `_vendor/`, or an import of the helper outside `boosting.py`, breaks this record.

**Scope:** `src/munin/core/boosting.py`; `src/munin/core/_vendor/klang/`

**Date:** 2026-10-27
