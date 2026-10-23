# ADR-0005: A Transcript ID is derived from its Source's key

**Decision:** The Transcript ID MUST be the first 12 hex characters of the SHA-256 of the Source's key, where a local Source's key is its resolved absolute path and a YouTube Source's key is its canonical watch URL, `https://www.youtube.com/watch?v=<id>`, and the ID MUST NOT be random or stored separately from that key.

**Reason:** A random ID kept next to the key in the cache was weighed and lost, because a derived ID makes "at most one Transcript per Source" hold by construction: the same Source always maps to the same ID, and a cache lookup is a file lookup with no index to keep in sync. For YouTube, using the bare video ID as the Transcript ID was weighed and lost, because it breaks the 12-hex shape every lookup validates and lets a video ID and a path hash share one namespace. Hashing `youtube:<id>` was weighed and lost to the canonical URL, which is the same string the Timestamp links start from.

**Consequence:** Moving or renaming a file gives it a new Transcript. Changing the file in place does not, since the path is the key. Every accepted URL form of one video shares one Transcript, so adding a URL form must map it to the same canonical URL. Any change to how paths resolve, such as `~` expansion or symlink handling, or to the canonical URL's shape, changes IDs and orphans existing cache entries.

**Scope:** `src/munin/core/transcribe.py`, `transcribe`

**Date:** 2026-10-22
