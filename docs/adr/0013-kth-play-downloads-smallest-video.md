# ADR-0013: A KTH Play download fetches the smallest video file

**Decision:** `download_smallest_video` MUST fetch the lowest-quality video file KTH Play offers for an entry, and MUST NOT pick a file by its picture quality.

**Reason:** KTH Play has no audio-only stream, so every download carries video that Munin throws away after decoding the sound. Fetching the best-quality file was weighed and lost. A lecture at high quality runs to gigabytes and takes minutes to download, while Pianissimo only gets 16 kHz mono audio, which the smallest file's sound track already covers.

**Consequence:** A KTH Play miss downloads the least data on offer. If KTH Play ever offers an audio-only stream, fetching that instead keeps to the spirit of this record but changes its Decision, so amend it. Choosing a file by resolution or bitrate of the picture breaks this record.

**Scope:** `src/munin/core/kthplay.py`, `download_smallest_video`

**Date:** 2026-10-24
