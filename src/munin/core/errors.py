"""Errors the core raises. Adapters turn these into their own error shape."""

from dataclasses import dataclass
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


class UnknownDeckError(MuninError):
    """No Deck read on its own has this ID.

    `deck_id` is the ID the caller gave, and the message names it, as in
    "No Deck with ID 0123456789ab".
    """

    def __init__(self, deck_id: str) -> None:
        super().__init__(f"No Deck with ID {deck_id}")


class VocabularyError(MuninError):
    """A Vocabulary's boost strength is outside 0 to 2.

    `alpha` is the strength the caller gave, and the message names it, as in
    "Boost strength 2.5 is outside 0 to 2".
    """

    def __init__(self, alpha: float) -> None:
        self.alpha = alpha
        super().__init__(f"Boost strength {alpha} is outside 0 to 2")


class LanguageError(MuninError):
    """A lecture language is anything but `sv` or `en`.

    `language` is the value the caller gave, and the message names it, as in
    "Language de is not sv or en".
    """

    def __init__(self, language: str) -> None:
        self.language = language
        super().__init__(f"Language {language} is not sv or en")


class EnglishVocabularyError(MuninError):
    """A call gave Vocabulary terms for an English lecture, which has no Vocabulary yet.

    The lecture is English when the call asks for `en`, or when it gives no
    language and the cached Transcript is English. The message tells the caller
    what to do: "Vocabulary terms do not work on English lectures yet. Call
    again without them."
    """

    def __init__(self) -> None:
        super().__init__("Vocabulary terms do not work on English lectures yet. Call again without them.")


class OutlineError(MuninError):
    """Base for every error that rejects an Outline before anything is rendered.

    Catch this to handle both `OutlineSyntaxError` and `OutlineStructureError`.
    """


class OutlineSyntaxError(OutlineError):
    """The Outline was given as text that is not JSON, such as a Markdown Outline.

    `line` and `column` are where parsing broke, both counted from 1, and
    `reason` is what the parser expected there, such as "Expecting value".
    The message names all three and ends by telling the LLM to call
    `get_outline_schema`, as in "Outline is not JSON: line 3, column 12:
    Expecting value. Call get_outline_schema to see the Outline format."
    """

    def __init__(self, line: int, column: int, reason: str) -> None:
        self.line = line
        self.column = column
        self.reason = reason
        super().__init__(
            f"Outline is not JSON: line {line}, column {column}: {reason}. {_SCHEMA_HINT}"
        )


@dataclass(frozen=True)
class OutlineProblem:
    """One thing wrong with an Outline, found before anything is rendered.

    `path` is the labels from the main topic down to the bad node, that node
    included, such as `("Matriser", "Determinanter", "Slide 4", "Determinant")`.
    A node whose label is missing, blank or not a string stands in the path as
    `#N`, its position among its siblings counted from 1, and a problem with
    the root itself has the empty path. `message` says what is wrong in one
    line, such as `stamp "1:75" is malformed`.
    """

    path: tuple[str, ...]
    message: str


class OutlineStructureError(OutlineError):
    """The Outline is JSON but breaks the schema, the nesting rules, or its Source or Deck.

    `problems` holds every problem the check found, at least one, in Outline
    order, parents before children and siblings in order. The message gives
    one problem per line, as the path joined by ` › `, a colon and the problem's
    message, such as `Matriser › Rader › #3: missing label`, with a problem at
    the root written as `Outline: <message>`. Its last line tells the LLM to
    call `get_outline_schema`, as in "Call get_outline_schema to see the
    Outline format."
    """

    def __init__(self, problems: tuple[OutlineProblem, ...]) -> None:
        self.problems = problems
        lines = [f"{' › '.join(problem.path) or 'Outline'}: {problem.message}" for problem in problems]
        super().__init__("\n".join([*lines, _SCHEMA_HINT]))


_SCHEMA_HINT = "Call get_outline_schema to see the Outline format."
