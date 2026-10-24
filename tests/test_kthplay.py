from pathlib import Path

import pytest

from munin.core import KthPlaySource, download_smallest_video, parse_kthplay_url

ENTRY_ID = "0_1zk8obn5"
FIXED_URL = f"https://play.kth.se/media/t/{ENTRY_ID}"
SHORT_ENTRY_ID = "0_kcveux4p"
SMALLEST_FILE_BYTES = 1_334_087


# Telling a KTH Play link apart


@pytest.mark.parametrize(
    "url",
    [
        f"https://play.kth.se/media/Matriser/{ENTRY_ID}",
        f"http://play.kth.se/media/Matriser/{ENTRY_ID}",
        f"play.kth.se/media/Matriser/{ENTRY_ID}",
        f"https://play.kth.se/media/t/{ENTRY_ID}",
        f"http://play.kth.se/media/t/{ENTRY_ID}",
        f"play.kth.se/media/t/{ENTRY_ID}",
        f"https://play.kth.se/media/{ENTRY_ID}",
        f"http://play.kth.se/media/{ENTRY_ID}",
        f"play.kth.se/media/{ENTRY_ID}",
        f"https://PLAY.KTH.SE/media/t/{ENTRY_ID}",
        f"https://play.kth.se/media/t/{ENTRY_ID}?st=90",
        f"https://play.kth.se/media/Matriser/{ENTRY_ID}#comments",
        f"https://play.kth.se/media/Matriser/{ENTRY_ID}/",
    ],
)
def test_kthplay_link_parses_to_its_entry_id(url: str):
    """Every accepted KTH Play link form parses to the video's entry ID."""
    assert parse_kthplay_url(url) == KthPlaySource(ENTRY_ID)


@pytest.mark.parametrize(
    "url",
    [
        "https://play.kth.se/channel/SF1624/123456",
        "https://play.kth.se/playlist/details/0_abcdefgh",
        "https://play.kth.se/search?keyword=matriser",
        "https://play.kth.se/media/Matriser/not-an-id",
        f"https://www.play.kth.se/media/t/{ENTRY_ID}",
        f"https://play.kth.se/media/Linjär/Algebra/{ENTRY_ID}",
        f"ftp://play.kth.se/media/t/{ENTRY_ID}",
        f"https://[play.kth.se/media/t/{ENTRY_ID}",
    ],
)
def test_non_video_kthplay_link_is_not_a_kthplay_source(url: str):
    """A link outside the three video shapes, schemes and host is not a KTH Play Source."""
    assert parse_kthplay_url(url) is None


# The KTH Play Source


def test_kthplay_url_is_fixed_lecture_address():
    """A KTH Play Source's url is its fixed lecture address."""
    assert KthPlaySource(ENTRY_ID).url == FIXED_URL


def test_kthplay_timestamp_url_appends_st():
    """A KTH Play Timestamp link is the fixed lecture address plus ?st=<seconds>."""
    assert KthPlaySource(ENTRY_ID).timestamp_url(274) == f"{FIXED_URL}?st=274"


# Real downloader


@pytest.mark.network
def test_real_kthplay_download_is_smallest_file_on_offer(tmp_path: Path):
    """The default KTH Play downloader fetches the smallest file on offer, mp4-666 of the short video, not the larger hls-715."""
    file = download_smallest_video(KthPlaySource(SHORT_ENTRY_ID), tmp_path)
    assert file.stat().st_size == SMALLEST_FILE_BYTES
