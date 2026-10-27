"""The core library. Plain Python, no transport. See ADR-0002."""

from munin.core.errors import (
    DeckError,
    KlangError,
    MuninError,
    NoSpeechError,
    OutlineError,
    SourceError,
    UnknownDeckError,
    UnknownTranscriptError,
    VocabularyError,
)
from munin.core.kthplay import KthPlaySource, download_smallest_video, parse_kthplay_url
from munin.core.mindmap import (
    RenderResult,
    UnlinkedSlide,
    UnlinkedStamp,
    render_deck_mindmap,
    render_mindmap,
)
from munin.core.model import Recognize, load_recognizer
from munin.core.segments import Fragment, Segment, merge_fragments
from munin.core.slides import DeckResult, Slide, read_deck, read_slides
from munin.core.sources import Download, Source, Video, parse_source
from munin.core.transcribe import TranscribeResult, get_transcript, transcribe
from munin.core.vocabulary import Vocabulary
from munin.core.youtube import YouTubeSource, download_audio, parse_youtube_url

__all__ = [
    "DeckError",
    "DeckResult",
    "Download",
    "Fragment",
    "KlangError",
    "KthPlaySource",
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
    "UnknownDeckError",
    "UnknownTranscriptError",
    "UnlinkedSlide",
    "UnlinkedStamp",
    "Video",
    "Vocabulary",
    "VocabularyError",
    "YouTubeSource",
    "download_audio",
    "download_smallest_video",
    "get_transcript",
    "load_recognizer",
    "merge_fragments",
    "parse_kthplay_url",
    "parse_source",
    "parse_youtube_url",
    "read_deck",
    "read_slides",
    "render_deck_mindmap",
    "render_mindmap",
    "transcribe",
]
