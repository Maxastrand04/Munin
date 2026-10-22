# ADR-0005: A local Transcript ID is derived from its Source path

**Decision:** The Transcript ID of a local Source MUST be the first 12 hex characters of the SHA-256 of the Source's resolved absolute path, and MUST NOT be random or stored separately from that path.

**Reason:** The alternative was a random ID kept next to the path in the cache. It lost because a derived ID makes "at most one Transcript per Source" hold by construction: the same file always maps to the same ID, and a cache lookup is a file lookup with no index to keep in sync.

**Consequence:** Moving or renaming a file gives it a new Transcript. Changing the file in place does not, since the path is the key. Any change to how paths resolve, such as `~` expansion or symlink handling, changes IDs and orphans existing cache entries. Accepting a YouTube URL needs its own key rule, which amends this record.

**Scope:** `src/klang_notes/core/transcribe.py`, `transcribe`

**Date:** 2026-10-22
