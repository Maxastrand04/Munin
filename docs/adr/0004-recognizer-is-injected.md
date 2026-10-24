# ADR-0004: The core takes its heavy external boundaries as arguments

**Decision:** Core functions that need speech recognition or a video download MUST accept a `Recognize` and a `Download` function as keyword-only arguments, and MUST fall back to `load_recognizer()` and the video site's default download, `download_audio` for YouTube or `download_smallest_video` for KTH Play, only when none was passed and the work is a cache miss.

**Reason:** Two alternatives were weighed. Running the real model and the real downloaders in every test is honest, but the model costs about 2.4 GB of RAM and seconds per test, the downloaders need the network, and "a cache hit loads no model and downloads nothing" has no way to be observed. Hardwiring them and monkeypatching in tests also works, but it ties tests to where the call happens inside the core. A class holding the cache folder and both dependencies would work too, but it adds an object nobody needs until the website adapter exists. The model and the video sites are heavy outside boundaries, like a database, so passing them in keeps the core's own logic testable with fakes.

**Consequence:** Loading the model or calling yt-dlp at import time, in a module-level global, or inside the MCP adapter breaks this record. Adapters pass `recognize` and `download` through and never call either themselves. One `download` argument serves every video site, so a passed `download` replaces each site's default. A test may fake either, but at least one test must run the real loader and one each site's real downloader, so the true paths get exercised.

**Scope:** `src/munin/core/transcribe.py`, `transcribe`; `src/munin/core/model.py`, `load_recognizer`; `src/munin/core/youtube.py`, `download_audio`; `src/munin/core/kthplay.py`, `download_smallest_video`

**Date:** 2026-10-24
