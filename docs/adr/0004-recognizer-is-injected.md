# ADR-0004: The core takes its recognizer as an argument

**Decision:** Core functions that need speech recognition MUST accept a `Recognize` function as a keyword-only argument and MUST load Pianissimo through `load_recognizer()` only when none was passed and the work is a cache miss.

**Reason:** Two alternatives were weighed. Running the real model in every test is honest but costs about 2.4 GB of RAM and seconds per test, and it leaves "a cache hit doesn't load the model" with no way to observe it. A class that holds the cache folder and a loaded model would also work, but it adds an object nobody needs until the website adapter exists. The model is a heavy external boundary, like a database, so passing it in keeps the core's own logic testable with a fake that yields canned fragments.

**Consequence:** Loading the model at import time, in a module-level global, or inside the MCP adapter breaks this record. Adapters pass `recognize` through and never call the model themselves. A test may fake `Recognize`, but at least one test must run the real loader so the true path gets exercised.

**Scope:** `src/klang_notes/core/transcribe.py`, `transcribe`; `src/klang_notes/core/model.py`, `load_recognizer`

**Date:** 2026-10-22
