"""The core library. Plain Python, no transport. See ADR-0002."""

from munin.core.errors import (
    DeckError,
    KlangError,
    MuninError,
    NoSpeechError,
    OutlineError,
    SourceError,
    UnknownTranscriptError,
    VocabularyError,
)
from munin.core.mindmap import RenderResult, UnlinkedSlide, UnlinkedStamp, render_mindmap
from munin.core.model import Recognize, load_recognizer
from munin.core.segments import Fragment, Segment, merge_fragments
from munin.core.slides import Slide, read_slides
from munin.core.sources import Source, parse_source
from munin.core.transcribe import TranscribeResult, get_transcript, transcribe
from munin.core.vocabulary import Vocabulary
from munin.core.youtube import Download, YouTubeSource, download_audio, parse_youtube_url

__all__ = [
    "DeckError",
    "Download",
    "Fragment",
    "KlangError",
    "MuninError",
    "NoSpeechError",
    "OutlineError",
    "Recognize",
    "RenderResult",
    "Segment",
    "Slide",
    "Source",
    "SourceError",
    "TranscribeResult",
    "UnknownTranscriptError",
    "UnlinkedSlide",
    "UnlinkedStamp",
    "Vocabulary",
    "VocabularyError",
    "YouTubeSource",
    "download_audio",
    "get_transcript",
    "load_recognizer",
    "merge_fragments",
    "parse_source",
    "parse_youtube_url",
    "read_slides",
    "render_mindmap",
    "transcribe",
]
