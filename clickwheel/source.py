"""yt-dlp wrapper: read metadata, download the best audio and its thumbnail.

yt-dlp does every network transfer (its chunked downloader avoids YouTube's
throttling); ffmpeg only ever reads local files.
"""

from __future__ import annotations

import logging
import re
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from .audio import Cancelled

log = logging.getLogger("clickwheel.source")

# Best audio-only stream (Opus 251 on YouTube), never the dynamic-range-compressed
# "drc" variants; fall back to a muxed stream when a video has no audio-only one.
AUDIO_FORMAT = "bestaudio[format_id!*=drc]/bestaudio/best"
JS_RUNTIMES = ("deno", "node", "bun")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class SourceError(Exception):
    """A user-facing failure: a short title, one line of advice, raw detail."""

    def __init__(self, title: str, message: str, detail: str = ""):
        super().__init__(f"{title} {message}")
        self.title = title
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class Download:
    info: dict
    audio: Path
    thumbnail: Path | None


@dataclass(frozen=True)
class FetchProgress:
    fraction: float
    speed: float | None = None
    eta: float | None = None


# (needles in yt-dlp's message, title, advice)
_KNOWN_ERRORS = (
    (("private video",), "PRIVATE VIDEO.", "Only its owner can play it."),
    (("confirm your age", "age-restricted", "inappropriate for some users"),
     "AGE RESTRICTED.", "This video needs a signed-in account."),
    (("not a bot",), "YOUTUBE BLOCKED THE REQUEST.", "Wait a few minutes, then retry."),
    (("members-only", "join this channel"), "MEMBERS ONLY.", "This video needs a channel membership."),
    (("live event will begin", "premieres in", "premiere will begin"),
     "NOT AIRED YET.", "Premieres download after they finish."),
    (("video unavailable", "has been removed", "no longer available", "does not exist"),
     "VIDEO UNAVAILABLE.", "Removed, region-locked, or the link is wrong."),
    (("requested format is not available",), "NO AUDIO STREAM.", "This video has no downloadable audio."),
)


def to_source_error(exc: Exception) -> SourceError:
    detail = _ANSI.sub("", str(exc)).removeprefix("ERROR: ").strip()[:300]
    lowered = detail.lower()
    for needles, title, message in _KNOWN_ERRORS:
        if any(n in lowered for n in needles):
            return SourceError(title, message, detail)
    return SourceError("SOURCE REFUSED.", "yt-dlp could not read this video. Retry, or update yt-dlp.", detail)


def check_playable(info: dict, max_duration_s: int) -> None:
    status = info.get("live_status")
    if status == "is_live" or info.get("is_live"):
        raise SourceError("LIVE STREAM.", "Streams have no end. Paste a mix or a finished video.")
    if status == "is_upcoming":
        raise SourceError("NOT AIRED YET.", "Premieres download after they finish.")
    if status == "post_live":
        raise SourceError("STILL PROCESSING.", "The stream just ended. Retry once YouTube finishes it.")
    duration = info.get("duration") or 0
    if duration <= 0:
        raise SourceError("NO DURATION.", "YouTube reports no length for this video.")
    if duration > max_duration_s:
        hours = max_duration_s / 3600
        raise SourceError(f"OVER {hours:g} HOURS.", "Raise CLICKWHEEL_MAX_DURATION_MIN to allow longer mixes.")


def js_runtime() -> str | None:
    return next((name for name in JS_RUNTIMES if shutil.which(name)), None)


class _Logger:
    """Route yt-dlp output to logging instead of the console."""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        log.warning(_ANSI.sub("", msg))

    def error(self, msg: str) -> None:
        log.error(_ANSI.sub("", msg))


def _options(**extra) -> dict:
    return {
        "format": AUDIO_FORMAT,
        "noplaylist": True,
        "allowed_extractors": ["youtube"],
        "js_runtimes": {name: {} for name in JS_RUNTIMES},
        "quiet": True,
        "noprogress": True,
        "logger": _Logger(),
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        **extra,
    }


def probe(url: str) -> dict:
    """Metadata only; nothing is downloaded."""
    try:
        with yt_dlp.YoutubeDL(_options()) as ydl:
            return ydl.sanitize_info(ydl.extract_info(url, download=False))
    except DownloadError as exc:
        raise to_source_error(exc) from exc


def fetch(
    url: str,
    dest: Path,
    on_progress: Callable[[FetchProgress], None],
    cancelled: threading.Event,
) -> Download:
    """Download the best audio stream and the thumbnail into dest."""
    dest.mkdir(parents=True, exist_ok=True)

    def hook(status: dict) -> None:
        if cancelled.is_set():
            raise DownloadCancelled()
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            done = status.get("downloaded_bytes") or 0
            fraction = min(1.0, done / total) if total else 0.0
            on_progress(FetchProgress(fraction, status.get("speed"), status.get("eta")))
        elif status.get("status") == "finished":
            on_progress(FetchProgress(1.0))

    options = _options(
        outtmpl={"default": str(dest / "source.%(ext)s"), "thumbnail": str(dest / "thumb.%(ext)s")},
        writethumbnail=True,
        overwrites=True,
        progress_hooks=[hook],
    )
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(url, download=True))
    except DownloadCancelled as exc:
        raise Cancelled() from exc
    except DownloadError as exc:
        if cancelled.is_set():
            raise Cancelled() from exc
        raise to_source_error(exc) from exc

    audio_path = _downloaded_file(info, dest)
    thumbs = sorted(p for p in dest.glob("thumb.*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    return Download(info=info, audio=audio_path, thumbnail=thumbs[0] if thumbs else None)


def _downloaded_file(info: dict, dest: Path) -> Path:
    for item in info.get("requested_downloads") or []:
        path = Path(item.get("filepath") or "")
        if path.is_file():
            return path
    found = sorted(dest.glob("source.*"))
    if not found:
        raise SourceError("DOWNLOAD MISSING.", "yt-dlp finished but wrote no audio file.")
    return found[0]
