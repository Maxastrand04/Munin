import pytest

from munin.core import Vocabulary, VocabularyError


def test_vocabulary_keeps_term_capitalisation():
    """Terms keep their capitalisation exactly as given."""
    assert Vocabulary(["SF1624", "Gausselimination", "pivotElement"]).terms == (
        "SF1624",
        "Gausselimination",
        "pivotElement",
    )


def test_vocabulary_strips_terms():
    """Whitespace around a term is stripped."""
    assert Vocabulary([" Gauss "]).terms == ("Gauss",)


def test_vocabulary_drops_blank_terms():
    """Empty and whitespace-only terms are dropped."""
    assert Vocabulary(["Gauss", "  ", ""]).terms == ("Gauss",)


def test_vocabulary_drops_duplicate_terms_keeping_first():
    """Exact duplicate terms collapse to their first occurrence, keeping order."""
    assert Vocabulary(["Gauss", "Matris", "Gauss"]).terms == ("Gauss", "Matris")


def test_vocabulary_alpha_defaults_to_one():
    """A Vocabulary built without alpha boosts at strength 1.0."""
    assert Vocabulary(["Gauss"]).alpha == 1.0


@pytest.mark.parametrize("alpha", [0.0, 2.0])
def test_vocabulary_accepts_alpha_at_bounds(alpha: float):
    """Both ends of the 0 to 2 range are valid boost strengths."""
    assert Vocabulary(["Gauss"], alpha).alpha == alpha


@pytest.mark.parametrize("alpha", [-0.1, 2.1, float("nan")])
def test_vocabulary_rejects_alpha_outside_range(alpha: float):
    """A boost strength below 0, above 2, or NaN raises VocabularyError."""
    with pytest.raises(VocabularyError):
        Vocabulary(["Gauss"], alpha)


def test_vocabulary_error_names_alpha():
    """The VocabularyError message names the strength the caller gave."""
    with pytest.raises(VocabularyError, match="2.5"):
        Vocabulary(["Gauss"], 2.5)
