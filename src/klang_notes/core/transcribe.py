"""Transcribing a local Source and reading its Transcript back."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path

from klang_notes.core.errors import NoSpeechError, SourceError, UnknownTranscriptError
from klang_notes.core.model import Recognize, load_recognizer
from klang_notes.core.segments import Segment, merge_fragments

_ID_PATTERN = re.compile(r"[0-9a-f]{12}")


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
    resolved = Path(os.fspath(source)).expanduser().resolve()
    transcript_id = _transcript_id(resolved)
    cache_dir = cache_dir or _default_cache_dir()
    entry = _entry_path(cache_dir, transcript_id)

    if entry.is_file():
        stored = json.loads(entry.read_text(encoding="utf-8"))
        return TranscribeResult(
            transcript_id=transcript_id,
            duration_s=stored["duration_s"],
            segment_count=len(stored["segments"]),
            transcription_s=stored["transcription_s"],
            cached=True,
        )

    if not resolved.is_file():
        raise SourceError(source, "no such file")

    with tempfile.TemporaryDirectory() as workdir:
        wav = Path(workdir, "audio.wav")
        _decode(source, resolved, wav)
        with wave.open(str(wav)) as w:
            duration_s = w.getnframes() / w.getframerate()
        recognize = recognize or load_recognizer()
        started = time.perf_counter()
        segments = merge_fragments(list(recognize(wav)))
        transcription_s = time.perf_counter() - started

    if not segments:
        raise NoSpeechError(source)

    _write_entry(
        entry,
        {
            "source": str(resolved),
            "duration_s": duration_s,
            "transcription_s": transcription_s,
            "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in segments],
        },
    )
    return TranscribeResult(transcript_id, duration_s, len(segments), transcription_s, cached=False)


def get_transcript(transcript_id: str, *, cache_dir: Path | None = None) -> str:
    """Return a cached Transcript as one `[m:ss] text` line per Segment.

    Lines are in time order and joined with newlines. Each stamp is the Segment's
    start rounded down to the whole second, with minutes counting past 59, so
    4503.9 s reads `[75:03]`.

    `cache_dir` defaults to the per-user cache folder for klang-notes.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID.
    """
    entry = _entry_path(cache_dir or _default_cache_dir(), transcript_id)
    if not _ID_PATTERN.fullmatch(transcript_id) or not entry.is_file():
        raise UnknownTranscriptError(transcript_id)
    stored = json.loads(entry.read_text(encoding="utf-8"))
    segments = [Segment(s["start"], s["end"], s["text"]) for s in stored["segments"]]
    return "\n".join(f"[{_stamp(s.start)}] {s.text}" for s in segments)


def _default_cache_dir() -> Path:
    return user_cache_path("klang-notes")


def _transcript_id(resolved: Path) -> str:
    return hashlib.sha256(str(resolved).encode()).hexdigest()[:12]


def _entry_path(cache_dir: Path, transcript_id: str) -> Path:
    return cache_dir / f"{transcript_id}.json"


def _stamp(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def _decode(given: str | os.PathLike[str], resolved: Path, wav: Path) -> None:
    command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(resolved), "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(wav)]
    try:
        done = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        raise SourceError(given, "ffmpeg is not installed") from None
    if done.returncode != 0 or not wav.is_file():
        reason = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "ffmpeg could not decode it"
        raise SourceError(given, reason)


def _write_entry(entry: Path, data: dict) -> None:
    entry.parent.mkdir(parents=True, exist_ok=True)
    partial = entry.with_suffix(".json.part")
    partial.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    partial.replace(entry)
