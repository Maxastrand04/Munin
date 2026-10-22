import shutil
from pathlib import Path

import pytest

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A copy of the speech fixture in a temp folder, so a test may change it."""
    path = tmp_path / "media" / "lecture.m4a"
    path.parent.mkdir()
    shutil.copy(SPEECH, path)
    return path


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"
