# ADR-0019: Every part of an Outline node is always present

**Decision:** Every node MUST carry every part its type has, and a part that may be empty MUST be written as `""` or `[]`, never left out.

**Reason:** Letting the LLM leave out an empty `stamps`, `slides`, `children`, `explanation`, `steps` or `answer` was weighed and lost. One fixed shape per type lets the LLM copy the samples and fill in values, and it makes a missing key always an error rather than sometimes a default.

**Consequence:** "Optional" in the Outline means a value that may be empty, and "required" means one that must be non-blank. Making a part required is then a change to which parts must be non-blank, not to which keys exist. A default for an absent part breaks this record.

**Scope:** `src/munin/core/outline.py`, `get_outline_schema` and the Outline check

**Date:** 2026-10-29
