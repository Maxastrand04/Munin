"""Errors the core raises. Adapters turn these into their own error shape."""

from pathlib import Path


class MuninError(Exception):
    """Base for every error the core raises on purpose."""


class KlangError(MuninError):
    """Base for errors that come from transcribing with Klang's Pianissimo model."""


class SourceError(MuninError):
    """The Source is not a file, a YouTube URL or a KTH Play video URL, ffmpeg cannot decode it, or its video cannot be downloaded.

    `path` is the path or URL as the caller gave it, or a video's canonical URL
    for a failed download, and the message names it.
    """

    def __init__(self, path: str | Path, reason: str) -> None:
        self.path = str(path)
        self.reason = reason
        super().__init__(f"Cannot read {self.path}: {reason}")


class DeckError(MuninError):
    """The Deck is not a file, is not a PDF that can be read, or has no pages.

    `path` is the path as the caller gave it, and `reason` is one of
    "not a file", "not a readable PDF" or "has no pages". The message names
    both, as in "Cannot read slides.pdf: has no pages".
    """

    def __init__(self, path: str | Path, reason: str) -> None:
        self.path = str(path)
        self.reason = reason
        super().__init__(f"Cannot read {self.path}: {reason}")


class NoSpeechError(KlangError):
    """The Source decoded, but VAD and Pianissimo found no non-empty speech in it.

    `path` is the path as the caller gave it, and the message names it.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        super().__init__(f"No speech found in {self.path}")


class UnknownTranscriptError(MuninError):
    """No cached Transcript has this ID.

    `transcript_id` is the ID the caller gave, and the message names it.
    """

    def __init__(self, transcript_id: str) -> None:
        self.transcript_id = transcript_id
        super().__init__(f"No Transcript with ID {transcript_id}")


class VocabularyError(MuninError):
    """A Vocabulary's boost strength is outside 0 to 2.

    `alpha` is the strength the caller gave, and the message names it, as in
    "Boost strength 2.5 is outside 0 to 2".
    """

    def __init__(self, alpha: float) -> None:
        self.alpha = alpha
        super().__init__(f"Boost strength {alpha} is outside 0 to 2")


class OutlineError(MuninError):
    """The Outline has no Markdown headings or list items, so it has no nodes to draw."""

    def __init__(self) -> None:
        super().__init__("Outline has no headings or list items to turn into Mindmap nodes")
