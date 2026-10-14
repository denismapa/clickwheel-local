"""Shared fixtures: synthetic sources made by ffmpeg, so tests run offline."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from clickwheel.audio import ffmpeg_bin

SOURCE_SECONDS = 12.0


def _ffmpeg(*args: str) -> None:
    subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="session")
def opus_source(media_dir) -> Path:
    """12 s stereo Opus in WebM at 48 kHz, like YouTube format 251."""
    path = media_dir / "source.webm"
    _ffmpeg(
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={SOURCE_SECONDS}",
        "-ac", "2", "-c:a", "libopus", "-b:a", "128k", str(path),
    )
    return path


@pytest.fixture(scope="session")
def aac_source(media_dir) -> Path:
    """4 s stereo AAC-LC at 44.1 kHz, like YouTube format 140."""
    path = media_dir / "source.m4a"
    _ffmpeg(
        "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=44100:duration=4",
        "-ac", "2", "-c:a", "aac", "-b:a", "128k", str(path),
    )
    return path


@pytest.fixture(scope="session")
def thumbnail(media_dir) -> Path:
    """A 16:9 thumbnail, like YouTube's maxresdefault."""
    path = media_dir / "thumb.jpg"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=1", "-frames:v", "1", "-update", "1", str(path))
    return path


def chapter_info(duration: float = SOURCE_SECONDS) -> dict:
    """A yt-dlp info dict for a 3-chapter lofi mix."""
    return {
        "id": "abcdefghijk",
        "title": "lofi hip hop mix 📚 beats to relax/study to",
        "channel": "Lofi Girl",
        "upload_date": "20240315",
        "duration": duration,
        "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "live_status": "not_live",
        "chapters": [
            {"start_time": 0.0, "end_time": 4.0, "title": "No Spirit - Memories We Made"},
            {"start_time": 4.0, "end_time": 8.0, "title": "S N U G, Mondo Loops - Night Coffee"},
            {"start_time": 8.0, "end_time": duration, "title": "Yasumu – We Met"},
        ],
    }
