import pytest

from munin.core import LanguageError, parse_language

BAD_LANGUAGES = ["de", "", "EN", "english", "sv "]


@pytest.mark.parametrize("language", ["sv", "en"])
def test_parse_language_returns_a_known_language(language: str):
    """`sv` and `en` come back as themselves."""
    assert parse_language(language) == language


def test_parse_language_returns_none_for_no_language():
    """None means the caller gave no language."""
    assert parse_language(None) is None


@pytest.mark.parametrize("language", BAD_LANGUAGES)
def test_parse_language_rejects_anything_else(language: str):
    """Anything but an exact `sv` or `en` raises LanguageError."""
    with pytest.raises(LanguageError):
        parse_language(language)


def test_language_error_names_the_value():
    """The error says which value was wrong and which values are right."""
    with pytest.raises(LanguageError, match="Language de is not sv or en"):
        parse_language("de")
