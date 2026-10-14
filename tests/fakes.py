"""Stand-ins for yt-dlp so pipeline, job and API tests run offline."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from clickwheel.audio import Cancelled
from clickwheel.config import Settings
from clickwheel.source import Download, FetchProgress

from .conftest import chapter_info


def settings_for(tmp_path: Path, **overrides) -> Settings:
    values = {
        "work_dir": tmp_path / "work",
        "allowed_hosts": ("testserver", "127.0.0.1", "localhost"),
        "encode_workers": 2,
        "open_browser": False,
    }
    return Settings(**{**values, **overrides})


def probe_info(**overrides) -> dict:
    """What source.probe returns for a chaptered lofi mix."""
    return {
        **chapter_info(),
        "format_id": "251",
        "acodec": "opus",
        "abr": 140.8,
        "asr": 48000,
        "thumbnail": "https://i.ytimg.com/vi/abcdefghijk/maxresdefault.webp",
        **overrides,
    }


class FakeFetcher:
    """Copies local media where yt-dlp would have written it."""

    def __init__(self, audio: Path, thumbnail: Path | None, info: dict | None = None,
                 gate: threading.Event | None = None):
        self.audio, self.thumbnail = audio, thumbnail
        self.info = info or chapter_info()
        self.gate = gate  # when set, fetch waits here until released or cancelled
        self.started = threading.Event()
        self.calls: list[str] = []

    def __call__(self, url: str, dest: Path, on_progress, cancelled) -> Download:
        self.calls.append(url)
        self.started.set()
        if self.gate is not None:
            while not self.gate.wait(0.02):
                if cancelled.is_set():
                    raise Cancelled()
        if cancelled.is_set():
            raise Cancelled()
        dest.mkdir(parents=True, exist_ok=True)
        for fraction in (0.25, 0.5, 1.0):
            on_progress(FetchProgress(fraction, speed=1_000_000.0, eta=1))
        audio = dest / f"source{self.audio.suffix}"
        shutil.copy(self.audio, audio)
        thumb = None
        if self.thumbnail is not None:
            thumb = dest / f"thumb{self.thumbnail.suffix}"
            shutil.copy(self.thumbnail, thumb)
        return Download(info={**self.info, "webpage_url": url}, audio=audio, thumbnail=thumb)
