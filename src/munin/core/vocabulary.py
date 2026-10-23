"""The terms, and how hard to boost them, that steer Pianissimo's spelling."""

from dataclasses import dataclass

from munin.core.errors import VocabularyError

_MIN_ALPHA = 0
_MAX_ALPHA = 2


@dataclass(frozen=True)
class Vocabulary:
    """Terms Pianissimo should spell as given, and the boost strength `alpha`.

    `terms` may be given as any iterable of strings and is stored as a tuple.
    Each term is stripped of surrounding whitespace, blank terms are dropped,
    and exact duplicates are dropped keeping the first, so order is otherwise
    kept. Capitalisation is never changed, since the decoder treats terms as
    case sensitive. A Vocabulary whose terms all turn out blank has no terms,
    and `transcribe` treats it as no Vocabulary.

    `alpha` is the boost strength, from 0 to 2 inclusive, default 1.0.

    Raises `VocabularyError` when `alpha` is below 0, above 2, or NaN.
    """

    terms: tuple[str, ...]
    alpha: float = 1.0

    def __post_init__(self) -> None:
        if not _MIN_ALPHA <= self.alpha <= _MAX_ALPHA:
            raise VocabularyError(self.alpha)
        stripped = (term.strip() for term in self.terms)
        object.__setattr__(self, "terms", tuple(dict.fromkeys(term for term in stripped if term)))
