# ADR-0023: Only the Swedish recognizer applies a Vocabulary

**Decision:** The recognizer `load_recognizer` returns MUST call `apply_vocabulary` only for `sv`, and MUST NOT call it on the English model.

**Reason:** Unknown. Found as a comment in `src/munin/core/model.py`, quoted:

> Boosting patches Pianissimo only. An English run has no Vocabulary, so there is nothing to boost.

**Consequence:** Klang's phrase boosting is written for Pianissimo, so the English recognizer never touches it, not even to reset boosting on a `None` call as ADR-0009 asks of the Swedish one. The English recognizer ignores any Vocabulary it is given, so `transcribe` must keep rejecting Vocabulary terms on English lectures before a run starts. Dropping the language check around `apply_vocabulary`, or boosting English without its own boosting path, breaks this record.

**Scope:** `src/munin/core/model.py`, `load_recognizer`

**Status:** found

**Date:** 2026-11-07
