"""The core library. Plain Python, no transport. See ADR-0002."""

from munin.core.errors import (
    DeckError,
    KlangError,
    LanguageError,
    MuninError,
    NoSpeechError,
    OutlineError,
    OutlineProblem,
    OutlineStructureError,
    OutlineSyntaxError,
    SourceError,
    UnknownDeckError,
    UnknownTranscriptError,
    VocabularyError,
)
from munin.core.kthplay import KthPlaySource, download_smallest_video, parse_kthplay_url
from munin.core.language import Language, parse_language
from munin.core.mindmap import (
    DrawnNode,
    DrawnOutline,
    ProseRun,
    RenderResult,
    TimestampLink,
    WorkedBox,
    WorkedStep,
    render_deck_mindmap,
    render_drawn_outline,
    render_mindmap,
)
from munin.core.model import Recognize, load_recognizer
from munin.core.outline import OutlineSchema, get_outline_schema
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
    "DrawnNode",
    "DrawnOutline",
    "Fragment",
    "KlangError",
    "KthPlaySource",
    "Language",
    "LanguageError",
    "MuninError",
    "NoSpeechError",
    "OutlineError",
    "OutlineProblem",
    "OutlineSchema",
    "OutlineStructureError",
    "OutlineSyntaxError",
    "ProseRun",
    "Recognize",
    "RenderResult",
    "Segment",
    "Slide",
    "Source",
    "SourceError",
    "TimestampLink",
    "TranscribeResult",
    "UnknownDeckError",
    "UnknownTranscriptError",
    "Video",
    "Vocabulary",
    "VocabularyError",
    "WorkedBox",
    "WorkedStep",
    "YouTubeSource",
    "download_audio",
    "download_smallest_video",
    "get_outline_schema",
    "get_transcript",
    "load_recognizer",
    "merge_fragments",
    "parse_kthplay_url",
    "parse_language",
    "parse_source",
    "parse_youtube_url",
    "read_deck",
    "read_slides",
    "render_deck_mindmap",
    "render_drawn_outline",
    "render_mindmap",
    "transcribe",
]
