# ADR-0012: Video sites reach yt-dlp through one module

**Decision:** Only `src/munin/core/ytdlp.py` MUST import or call yt-dlp, and each video site's module, such as `youtube.py` or `kthplay.py`, MUST fetch its downloads through it.

**Reason:** KTH Play is the second site that yt-dlp downloads from, so PCR-0004 forced a choice about where yt-dlp lives. Two alternatives were weighed. Putting KTH Play into `youtube.py` keeps yt-dlp where it was, but it makes one module change for two unrelated sites. Renaming `youtube.py` into one video module for every site has the same problem and grows with each university added later. A yt-dlp module of its own lets each site module stay about its own URLs, links and download choice.

**Consequence:** A site module knows its URL forms, its canonical address and what it downloads, and leaves the yt-dlp call to `ytdlp.py`. Adding a site, as the later ticket for other universities will, means a new site module and no new yt-dlp import. An `import yt_dlp` in any site module breaks this record.

**Scope:** `src/munin/core/ytdlp.py`; `src/munin/core/youtube.py`, `download_audio`; `src/munin/core/kthplay.py`, `download_smallest_video`

**Date:** 2026-10-24
