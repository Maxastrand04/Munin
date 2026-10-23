"""The core library. Plain Python, no transport. See ADR-0002."""

from klang_notes.core.errors import (
    KlangError,
    NoSpeechError,
    OutlineError,
    SourceError,
    UnknownTranscriptError,
)
from klang_notes.core.mindmap import RenderResult, UnlinkedStamp, render_mindmap
from klang_notes.core.model import Recognize, load_recognizer
from klang_notes.core.segments import Fragment, Segment, merge_fragments
from klang_notes.core.sources import Source, parse_source
from klang_notes.core.transcribe import TranscribeResult, get_transcript, transcribe
from klang_notes.core.youtube import Download, YouTubeSource, download_audio, parse_youtube_url

__all__ = [
    "Download",
    "Fragment",
    "KlangError",
    "NoSpeechError",
    "OutlineError",
    "Recognize",
    "RenderResult",
    "Segment",
    "Source",
    "SourceError",
    "TranscribeResult",
    "UnknownTranscriptError",
    "UnlinkedStamp",
    "YouTubeSource",
    "download_audio",
    "get_transcript",
    "load_recognizer",
    "merge_fragments",
    "parse_source",
    "parse_youtube_url",
    "render_mindmap",
    "transcribe",
]
