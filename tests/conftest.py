import shutil
import wave
from pathlib import Path

import pytest

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
SAMPLE_RATE = 16_000


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


@pytest.fixture
def five_second_source(tmp_path: Path) -> Path:
    """A WAV of exactly 5.0 s of silence, so stamps can sit on the Source's end to the second."""
    path = tmp_path / "media" / "five_seconds.wav"
    path.parent.mkdir(exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(bytes(2 * 5 * SAMPLE_RATE))
    return path
