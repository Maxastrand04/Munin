from munin.core import KthPlaySource, parse_source


def test_parse_source_returns_kthplay_source_for_kthplay_link():
    """parse_source turns a KTH Play video link into a KTH Play Source, not a Path."""
    assert parse_source("https://play.kth.se/media/Föreläsning+4A+Matriser/0_1zk8obn5") == KthPlaySource("0_1zk8obn5")
