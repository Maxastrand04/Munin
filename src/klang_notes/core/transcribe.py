"""Transcribing a local Source and reading its Transcript back."""

import os
from dataclasses import dataclass
from pathlib import Path

from klang_notes.core.model import Recognize


@dataclass(frozen=True)
class TranscribeResult:
    """What `transcribe` tells the caller about a Transcript.

    `duration_s` is the Source's audio length in seconds. `transcription_s` is how
    long the run that made the Transcript took, so a cache hit reports the original
    run's time. `cached` is True when no transcription ran for this call.
    """

    transcript_id: str
    duration_s: float
    segment_count: int
    transcription_s: float
    cached: bool


def transcribe(
    source: str | os.PathLike[str],
    *,
    cache_dir: Path | None = None,
    recognize: Recognize | None = None,
) -> TranscribeResult:
    """Transcribe a local audio or video file, or return its cached Transcript.

    The path has `~` expanded and is resolved to an absolute path. That resolved
    path is the cache key, so relative, `~` and absolute forms of one file share
    one Transcript. The Transcript ID is the first 12 hex characters of the
    SHA-256 of the resolved path. A cached Transcript is returned as is, even if
    the file changed since, and no recognizer is loaded or called.

    On a miss, the file is decoded with ffmpeg to 16 kHz mono and passed to
    `recognize`, whose fragments go through `merge_fragments`. The Transcript and
    its Source are then written to the cache.

    `cache_dir` defaults to the per-user cache folder for klang-notes.
    `recognize` defaults to `load_recognizer()`, called only on a miss.

    Raises `SourceError` when the path does not exist, is not a file, or ffmpeg
    cannot decode it. Raises `NoSpeechError` when no non-empty Segment comes out.
    Neither writes anything to the cache.
    """
    raise NotImplementedError


def get_transcript(transcript_id: str, *, cache_dir: Path | None = None) -> str:
    """Return a cached Transcript as one `[m:ss] text` line per Segment.

    Lines are in time order and joined with newlines. Each stamp is the Segment's
    start rounded down to the whole second, with minutes counting past 59, so
    4503.9 s reads `[75:03]`.

    `cache_dir` defaults to the per-user cache folder for klang-notes.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID.
    """
    raise NotImplementedError
