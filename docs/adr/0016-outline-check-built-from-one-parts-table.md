# ADR-0016: The Outline schema and check are built from one parts table

**Decision:** `get_outline_schema`'s JSON Schema and the check every render runs MUST both be built from one table in `outline.py` that lists each node type's parts and which must be non-blank, with the standard library only, and MUST NOT use `jsonschema`, `pydantic` or another validation library.

**Reason:** Validating with `jsonschema` against the schema dict was weighed and lost, because its nesting errors read "is not valid under any of the given schemas" and its paths are list indexes, while the check must list every problem by the labels from the main topic down. `pydantic` models with `model_json_schema()` lost for the same reason about paths, and either one would be a new declared dependency with its own module under PCR-0004. A hand-written check over one table gives the messages the LLM needs and keeps the schema the LLM reads and the rules the renderer enforces from drifting apart.

**Consequence:** Making a part required, or adding one, is a change to that one table, and the schema and the check follow. A second copy of the rules, such as a hand-maintained schema dict beside the check, or an `import jsonschema` or `import pydantic` in the core, breaks this record.

**Scope:** `src/munin/core/outline.py`, `get_outline_schema` and the Outline check

**Date:** 2026-10-29
