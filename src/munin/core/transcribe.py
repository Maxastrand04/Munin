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

from munin.core.cache_paths import default_cache_dir
from munin.core.decode import decode_to_wav
from munin.core.errors import NoSpeechError, SourceError, UnknownTranscriptError
from munin.core.model import Recognize, load_recognizer
from munin.core.segments import Segment, merge_fragments
from munin.core.sources import Download, Source, parse_source
from munin.core.stamps import format_stamp
from munin.core.vocabulary import Vocabulary
from munin.core.youtube import YouTubeSource, download_audio

_ID_LENGTH = 12
_ID_PATTERN = re.compile(f"[0-9a-f]{{{_ID_LENGTH}}}")


@dataclass(frozen=True)
class TranscribeResult:
    """What `transcribe` tells the caller about a Transcript.

    `duration_s` is the Source's audio length in seconds. `transcription_s` is how
    long the run that made the Transcript took, so a cache hit reports the original
    run's time. `cached` is True when no transcription ran for this call.

    `vocabulary` is the Vocabulary the cached Transcript was made with, or None
    when it was made without one. A cache hit reports the stored one.
    """

    transcript_id: str
    duration_s: float
    segment_count: int
    transcription_s: float
    cached: bool
    vocabulary: Vocabulary | None = None


@dataclass(frozen=True)
class CacheEntry:
    """A cached Transcript and what is known about its Source.

    `source` is a local Source's resolved absolute path, or for YouTube and KTH
    Play the video, never the file downloaded to transcribe it. `duration_s` is the
    Source's audio length in seconds, `transcription_s` how long the run that
    made the Transcript took, and `segments` the Transcript in time order.
    """

    source: Source
    duration_s: float
    transcription_s: float
    segments: tuple[Segment, ...]
    vocabulary: Vocabulary | None = None

    def _result(self, transcript_id: str, *, cached: bool) -> TranscribeResult:
        """Return this entry as the `TranscribeResult` for `transcript_id`, marked `cached` or not."""
        return TranscribeResult(
            transcript_id, self.duration_s, len(self.segments), self.transcription_s, cached, self.vocabulary
        )


def transcribe(
    source: str | os.PathLike[str],
    *,
    vocabulary: Vocabulary | None = None,
    cache_dir: Path | None = None,
    recognize: Recognize | None = None,
    download: Download | None = None,
) -> TranscribeResult:
    """Transcribe a local audio or video file, a YouTube video or a KTH Play video, or return its cached Transcript.

    `source` goes through `parse_source`, so a YouTube video URL is a YouTube
    Source, a KTH Play video URL is a KTH Play Source, and anything else is a
    local path.

    A local path has `~` expanded and is resolved to an absolute path. That
    resolved path is the cache key, so relative, `~` and absolute forms of one
    file share one Transcript. A YouTube Source's key is its canonical `url`, and
    a KTH Play Source's key is its fixed lecture address `url`, so every accepted
    URL form of one video shares one Transcript. The Transcript ID
    is the first 12 hex characters of the SHA-256 of the key. A cached Transcript
    is returned as is, even if the file changed since, and nothing is downloaded,
    and no recognizer is loaded or called.

    A `vocabulary` with terms always runs a fresh transcription, even when the
    cache holds a Transcript for this Source, and reports `cached=False`. The
    Vocabulary reaches `recognize` unchanged. On success the new Transcript
    replaces the cached one under the same Transcript ID, stored with its
    Vocabulary. A `vocabulary` with no terms counts as None. With no Vocabulary,
    a cached Transcript is returned as is, whether it was boosted or not, and
    `recognize` receives None on a miss.

    On a miss, a YouTube Source's audio, or a KTH Play Source's video file, is
    first fetched with `download` into a temporary work folder. The file, or the
    downloaded audio or video, is decoded with ffmpeg to 16 kHz mono and passed
    to `recognize`, whose fragments go through `merge_fragments`. The Transcript
    and its Source are then written to the cache. For a YouTube or KTH Play
    Source the cached Source is the video, not the downloaded file, and the work
    folder and the download in it are deleted before returning.
    `transcription_s` never includes download time.

    `cache_dir` defaults to the per-user cache folder for Munin.
    `recognize` defaults to `load_recognizer()`, called only on a miss.
    `download` defaults to `download_audio` for YouTube and
    `download_smallest_video` for KTH Play, called only on a miss for either.

    Raises `SourceError` when `source` is not an existing file, a YouTube video
    URL or a KTH Play video URL, with the reason "not a file, a YouTube URL or a
    KTH Play video URL", when ffmpeg cannot decode it, or when `download`
    cannot fetch the video. Raises `NoSpeechError` when no non-empty Segment
    comes out. None of these writes anything to the cache, so a failed boosted
    run leaves the previously cached Transcript in place.
    """
    parsed = parse_source(source)
    resolved = parsed.expanduser().resolve() if isinstance(parsed, Path) else parsed
    transcript_id = _transcript_id(_source_key(resolved))
    entry_path = _entry_path(cache_dir, transcript_id)
    vocabulary = vocabulary if vocabulary and vocabulary.terms else None
    if vocabulary is None and entry_path.is_file():
        return _read_entry(entry_path)._result(transcript_id, cached=True)
    if isinstance(resolved, YouTubeSource):
        entry = _transcribe_video(resolved, entry_path.parent, download, recognize, vocabulary)
    else:
        entry = _transcribe_fresh(source, resolved, recognize, vocabulary)
    _write_entry(entry_path, entry)
    return entry._result(transcript_id, cached=False)


def get_transcript(transcript_id: str, *, cache_dir: Path | None = None) -> str:
    """Return a cached Transcript as one `[m:ss] text` line per Segment.

    Lines are in time order and joined with newlines. Each stamp is the Segment's
    start rounded down to the whole second, with minutes counting past 59, so
    4503.9 s reads `[75:03]`.

    `cache_dir` defaults to the per-user cache folder for Munin.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID.
    """
    segments = cached_entry(transcript_id, cache_dir=cache_dir).segments
    return "\n".join(f"[{format_stamp(s.start)}] {s.text}" for s in segments)


def cached_entry(transcript_id: str, *, cache_dir: Path | None = None) -> CacheEntry:
    """Return the cached Transcript with this ID.

    `cache_dir` defaults to the per-user cache folder for Munin.

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
    video: YouTubeSource,
    cache_folder: Path,
    download: Download | None,
    recognize: Recognize | None,
    vocabulary: Vocabulary | None,
) -> CacheEntry:
    cache_folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache_folder) as workdir:
        audio = (download or download_audio)(video, Path(workdir))
        return replace(_transcribe_fresh(video.url, audio, recognize, vocabulary), source=video)


def _transcribe_fresh(
    given: str | os.PathLike[str], resolved: Path, recognize: Recognize | None, vocabulary: Vocabulary | None
) -> CacheEntry:
    if not resolved.is_file():
        raise SourceError(given, "not a file or a YouTube URL")
    with tempfile.TemporaryDirectory() as workdir:
        wav = Path(workdir, "audio.wav")
        decode_to_wav(given, resolved, wav)
        duration_s = _duration_s(wav)
        recognize = recognize or load_recognizer()
        started = time.perf_counter()
        segments = merge_fragments(list(recognize(wav, vocabulary)))
        transcription_s = time.perf_counter() - started
    if not segments:
        raise NoSpeechError(given)
    return CacheEntry(resolved, duration_s, transcription_s, tuple(segments), vocabulary)


def _duration_s(wav: Path) -> float:
    with wave.open(str(wav)) as audio:
        return audio.getnframes() / audio.getframerate()


def _read_entry(entry_path: Path) -> CacheEntry:
    stored = json.loads(entry_path.read_text(encoding="utf-8"))
    stored_vocabulary = stored.get("vocabulary")
    return CacheEntry(
        source=parse_source(stored["source"]),
        duration_s=stored["duration_s"],
        transcription_s=stored["transcription_s"],
        segments=tuple(Segment(s["start"], s["end"], s["text"]) for s in stored["segments"]),
        vocabulary=Vocabulary(stored_vocabulary["terms"], stored_vocabulary["alpha"]) if stored_vocabulary else None,
    )


def _write_entry(entry_path: Path, entry: CacheEntry) -> None:
    stored = {
        "source": _source_key(entry.source),
        "duration_s": entry.duration_s,
        "transcription_s": entry.transcription_s,
        "segments": [asdict(s) for s in entry.segments],
        "vocabulary": asdict(entry.vocabulary) if entry.vocabulary else None,
    }
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    partial = entry_path.with_suffix(".json.part")
    partial.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    partial.replace(entry_path)
