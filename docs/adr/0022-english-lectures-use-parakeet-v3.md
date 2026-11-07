# ADR-0022: English lectures use Parakeet TDT 0.6B v3

**Decision:** Transcribing an English lecture MUST load Parakeet TDT 0.6B v3 from `istupakov/parakeet-tdt-0.6b-v3-onnx` with `quantization="int8"`, following the repo's main branch.

**Reason:** The report in [docs/research/english-lecture-model.md](../research/english-lecture-model.md) weighed the models onnx-asr can load. Parakeet v2 is the named fallback, but v3 passed on the 6:32 ID1200 clip on an M1 Pro: 0.71 to 0.77 of Pianissimo's time, 2.47 GB peak memory, 10 of 10 Segment starts within 2 s and no language drift ([PR #60](https://github.com/Maxastrand04/Munin/pull/60)), so the fallback isn't needed, and its boosting would need its own tokenizer. English Pianissimo is not published, and nothing in the epic waits for it. That prototype covered one speaker for 6:32, so memory on a full-length lecture and drift on a heavier accent are unmeasured.

**Consequence:** `load_recognizer("en")` loads this model and no other. onnx-asr 0.12.0 can neither force English nor pin a revision, so a change on the repo's main branch reaches Munin on the next download, and a lecturer's accent can drift out of English. Moving to another model, v2 or English Pianissimo included, is a new decision that amends this record with fresh measurements. The report lists the steps for English Pianissimo.

**Scope:** `src/munin/core/model.py`, `load_recognizer`

**Date:** 2026-11-07
