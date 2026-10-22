"""Transcribing a local Source and reading its Transcript back."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_cache_path

from klang_notes.core.errors import NoSpeechError, SourceError, UnknownTranscriptError
from klang_notes.core.model import Recognize, load_recognizer
from klang_notes.core.segments import Segment, merge_fragments

_APP_NAME = "klang-notes"
_ID_LENGTH = 12
_ID_PATTERN = re.compile(f"[0-9a-f]{{{_ID_LENGTH}}}")
_SAMPLE_RATE_HZ = 16000
_MONO = 1
_SECONDS_PER_MINUTE = 60


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


@dataclass(frozen=True)
class _CacheEntry:
    source: Path
    duration_s: float
    transcription_s: float
    segments: tuple[Segment, ...]

    def result(self, transcript_id: str, *, cached: bool) -> TranscribeResult:
        return TranscribeResult(transcript_id, self.duration_s, len(self.segments), self.transcription_s, cached)


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
    entry_path = _entry_path(cache_dir, transcript_id)
    if entry_path.is_file():
        return _read_entry(entry_path).result(transcript_id, cached=True)
    entry = _transcribe_fresh(source, resolved, recognize)
    _write_entry(entry_path, entry)
    return entry.result(transcript_id, cached=False)


def get_transcript(transcript_id: str, *, cache_dir: Path | None = None) -> str:
    """Return a cached Transcript as one `[m:ss] text` line per Segment.

    Lines are in time order and joined with newlines. Each stamp is the Segment's
    start rounded down to the whole second, with minutes counting past 59, so
    4503.9 s reads `[75:03]`.

    `cache_dir` defaults to the per-user cache folder for klang-notes.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID.
    """
    entry_path = _entry_path(cache_dir, transcript_id)
    if not _ID_PATTERN.fullmatch(transcript_id) or not entry_path.is_file():
        raise UnknownTranscriptError(transcript_id)
    segments = _read_entry(entry_path).segments
    return "\n".join(f"[{_stamp(s.start)}] {s.text}" for s in segments)


def _transcript_id(resolved: Path) -> str:
    return hashlib.sha256(str(resolved).encode()).hexdigest()[:_ID_LENGTH]


def _entry_path(cache_dir: Path | None, transcript_id: str) -> Path:
    return (cache_dir or user_cache_path(_APP_NAME)) / f"{transcript_id}.json"


def _transcribe_fresh(
    given: str | os.PathLike[str], resolved: Path, recognize: Recognize | None
) -> _CacheEntry:
    if not resolved.is_file():
        raise SourceError(given, "no such file")
    with tempfile.TemporaryDirectory() as workdir:
        wav = Path(workdir, "audio.wav")
        _decode_to_wav(given, resolved, wav)
        duration_s = _duration_s(wav)
        recognize = recognize or load_recognizer()
        started = time.perf_counter()
        segments = merge_fragments(list(recognize(wav)))
        transcription_s = time.perf_counter() - started
    if not segments:
        raise NoSpeechError(given)
    return _CacheEntry(resolved, duration_s, transcription_s, tuple(segments))


def _decode_to_wav(given: str | os.PathLike[str], resolved: Path, wav: Path) -> None:
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(resolved), "-vn",
        "-ac", str(_MONO), "-ar", str(_SAMPLE_RATE_HZ), "-f", "wav", str(wav),
    ]
    try:
        ffmpeg = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        raise SourceError(given, "ffmpeg is not installed") from None
    if ffmpeg.returncode != 0 or not wav.is_file():
        raise SourceError(given, _last_line(ffmpeg.stderr) or "ffmpeg could not decode it")


def _last_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[-1] if lines else ""


def _duration_s(wav: Path) -> float:
    with wave.open(str(wav)) as audio:
        return audio.getnframes() / audio.getframerate()


def _stamp(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), _SECONDS_PER_MINUTE)
    return f"{minutes}:{secs:02d}"


def _read_entry(entry_path: Path) -> _CacheEntry:
    stored = json.loads(entry_path.read_text(encoding="utf-8"))
    return _CacheEntry(
        source=Path(stored["source"]),
        duration_s=stored["duration_s"],
        transcription_s=stored["transcription_s"],
        segments=tuple(Segment(s["start"], s["end"], s["text"]) for s in stored["segments"]),
    )


def _write_entry(entry_path: Path, entry: _CacheEntry) -> None:
    stored = {
        "source": str(entry.source),
        "duration_s": entry.duration_s,
        "transcription_s": entry.transcription_s,
        "segments": [asdict(s) for s in entry.segments],
    }
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    partial = entry_path.with_suffix(".json.part")
    partial.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    partial.replace(entry_path)
