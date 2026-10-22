"""The core library. Plain Python, no transport. See ADR-0002."""

from klang_notes.core.errors import KlangError, NoSpeechError, SourceError, UnknownTranscriptError
from klang_notes.core.mindmap import render_mindmap
from klang_notes.core.model import Recognize, load_recognizer
from klang_notes.core.segments import Fragment, Segment, merge_fragments
from klang_notes.core.transcribe import TranscribeResult, get_transcript, transcribe

__all__ = [
    "Fragment",
    "KlangError",
    "NoSpeechError",
    "Recognize",
    "Segment",
    "SourceError",
    "TranscribeResult",
    "UnknownTranscriptError",
    "get_transcript",
    "load_recognizer",
    "merge_fragments",
    "render_mindmap",
    "transcribe",
]
