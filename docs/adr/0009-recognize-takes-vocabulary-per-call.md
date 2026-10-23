# ADR-0009: A Recognize function takes the Vocabulary on every call

**Decision:** A `Recognize` function MUST take the Vocabulary, or `None`, as its second argument on every call and MUST apply only that call's Vocabulary, so a call with `None` after a boosted call runs unboosted.

**Reason:** Two alternatives were weighed. Building the boost into `load_recognizer(vocabulary)` keeps `Recognize` at one argument, but an injected recognizer, which ADR-0004 requires the core to accept, could then never be boosted, and no test could see the terms reach it. An optional keyword that `transcribe` passes only when there is a Vocabulary keeps old one-argument fakes working, but leaves a "sometimes passed" rule in the contract for good. A required second argument is the shape every caller and fake can rely on. Applying only the current call's Vocabulary matters because Klang's boosting patches the loaded model in place, and a boost that outlived its call would quietly steer the next Source's Transcript.

**Consequence:** `transcribe` always passes the Vocabulary or `None`, and every fake recognizer takes two arguments. The real recognizer resets boosting on a `None` call, since one loaded model may serve many calls. A recognizer that caches the last Vocabulary, or skips the reset because today's adapter loads a fresh model per cache miss, breaks this record.

**Scope:** `src/munin/core/model.py`, `Recognize` and `load_recognizer`; `src/munin/core/transcribe.py`, `transcribe`

**Date:** 2026-10-23
