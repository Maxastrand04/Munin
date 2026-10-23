"""Transcribing a Source and reading its Transcript back."""

import hashlib
import json
import os
import re
import tempfile
import time
import wave
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from klang_notes.core.cache_paths import default_cache_dir
from klang_notes.core.decode import decode_to_wav
from klang_notes.core.errors import NoSpeechError, SourceError, UnknownTranscriptError
from klang_notes.core.model import Recognize, load_recognizer
from klang_notes.core.segments import Segment, merge_fragments
from klang_notes.core.sources import Source, parse_source
from klang_notes.core.stamps import format_stamp
from klang_notes.core.youtube import Download, YouTubeSource, download_audio

_ID_LENGTH = 12
_ID_PATTERN = re.compile(f"[0-9a-f]{{{_ID_LENGTH}}}")


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
class CacheEntry:
    """A cached Transcript and what is known about its Source.

    `source` is a local Source's resolved absolute path, or for YouTube the
    video, never the audio file downloaded to transcribe it. `duration_s` is the
    Source's audio length in seconds, `transcription_s` how long the run that
    made the Transcript took, and `segments` the Transcript in time order.
    """

    source: Source
    duration_s: float
    transcription_s: float
    segments: tuple[Segment, ...]

    def result(self, transcript_id: str, *, cached: bool) -> TranscribeResult:
        """Return this entry as the `TranscribeResult` for `transcript_id`, marked `cached` or not."""
        return TranscribeResult(transcript_id, self.duration_s, len(self.segments), self.transcription_s, cached)


def transcribe(
    source: str | os.PathLike[str],
    *,
    cache_dir: Path | None = None,
    recognize: Recognize | None = None,
    download: Download | None = None,
) -> TranscribeResult:
    """Transcribe a local audio or video file or a YouTube video, or return its cached Transcript.

    `source` goes through `parse_source`, so a YouTube video URL is a YouTube
    Source and anything else is a local path.

    A local path has `~` expanded and is resolved to an absolute path. That
    resolved path is the cache key, so relative, `~` and absolute forms of one
    file share one Transcript. A YouTube Source's key is its canonical `url`, so
    every accepted URL form of one video shares one Transcript. The Transcript ID
    is the first 12 hex characters of the SHA-256 of the key. A cached Transcript
    is returned as is, even if the file changed since, and nothing is downloaded,
    and no recognizer is loaded or called.

    On a miss, a YouTube Source's audio is first fetched with `download` into a
    temporary work folder. The file, or the downloaded audio, is decoded with
    ffmpeg to 16 kHz mono and passed to `recognize`, whose fragments go through
    `merge_fragments`. The Transcript and its Source are then written to the
    cache. For YouTube the cached Source is the video, not the downloaded file,
    and the work folder and the audio in it are deleted before returning.
    `transcription_s` never includes download time.

    `cache_dir` defaults to the per-user cache folder for klang-notes.
    `recognize` defaults to `load_recognizer()`, called only on a miss.
    `download` defaults to `download_audio`, called only on a YouTube miss.

    Raises `SourceError` when `source` is neither an existing file nor a YouTube
    video URL, with the reason "not a file or a YouTube URL", when ffmpeg cannot
    decode it, or when `download` cannot fetch the video. Raises `NoSpeechError`
    when no non-empty Segment comes out. None of these writes anything to the
    cache.
    """
    parsed = parse_source(source)
    resolved = parsed.expanduser().resolve() if isinstance(parsed, Path) else parsed
    transcript_id = _transcript_id(_source_key(resolved))
    entry_path = _entry_path(cache_dir, transcript_id)
    if entry_path.is_file():
        return _read_entry(entry_path).result(transcript_id, cached=True)
    if isinstance(resolved, YouTubeSource):
        entry = _transcribe_video(resolved, entry_path.parent, download, recognize)
    else:
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
    segments = cached_entry(transcript_id, cache_dir=cache_dir).segments
    return "\n".join(f"[{format_stamp(s.start)}] {s.text}" for s in segments)


def cached_entry(transcript_id: str, *, cache_dir: Path | None = None) -> CacheEntry:
    """Return the cached Transcript with this ID.

    `cache_dir` defaults to the per-user cache folder for klang-notes.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID.
    """
    entry_path = _entry_path(cache_dir, transcript_id)
    if not _ID_PATTERN.fullmatch(transcript_id) or not entry_path.is_file():
        raise UnknownTranscriptError(transcript_id)
    return _read_entry(entry_path)


def _source_key(source: Source) -> str:
    return source.url if isinstance(source, YouTubeSource) else str(source)


def _transcript_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:_ID_LENGTH]


def _entry_path(cache_dir: Path | None, transcript_id: str) -> Path:
    return (cache_dir or default_cache_dir()) / f"{transcript_id}.json"


def _transcribe_video(
    video: YouTubeSource, cache_folder: Path, download: Download | None, recognize: Recognize | None
) -> CacheEntry:
    cache_folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache_folder) as workdir:
        audio = (download or download_audio)(video, Path(workdir))
        return replace(_transcribe_fresh(video.url, audio, recognize), source=video)


def _transcribe_fresh(
    given: str | os.PathLike[str], resolved: Path, recognize: Recognize | None
) -> CacheEntry:
    if not resolved.is_file():
        raise SourceError(given, "not a file or a YouTube URL")
    with tempfile.TemporaryDirectory() as workdir:
        wav = Path(workdir, "audio.wav")
        decode_to_wav(given, resolved, wav)
        duration_s = _duration_s(wav)
        recognize = recognize or load_recognizer()
        started = time.perf_counter()
        segments = merge_fragments(list(recognize(wav)))
        transcription_s = time.perf_counter() - started
    if not segments:
        raise NoSpeechError(given)
    return CacheEntry(resolved, duration_s, transcription_s, tuple(segments))


def _duration_s(wav: Path) -> float:
    with wave.open(str(wav)) as audio:
        return audio.getnframes() / audio.getframerate()


def _read_entry(entry_path: Path) -> CacheEntry:
    stored = json.loads(entry_path.read_text(encoding="utf-8"))
    return CacheEntry(
        source=parse_source(stored["source"]),
        duration_s=stored["duration_s"],
        transcription_s=stored["transcription_s"],
        segments=tuple(Segment(s["start"], s["end"], s["text"]) for s in stored["segments"]),
    )


def _write_entry(entry_path: Path, entry: CacheEntry) -> None:
    stored = {
        "source": _source_key(entry.source),
        "duration_s": entry.duration_s,
        "transcription_s": entry.transcription_s,
        "segments": [asdict(s) for s in entry.segments],
    }
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    partial = entry_path.with_suffix(".json.part")
    partial.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    partial.replace(entry_path)
