"""The analyze response: what the iPod will get, before anything downloads."""

from __future__ import annotations

from urllib.parse import urlsplit

from .config import Settings
from .source import check_playable
from .textutil import clean_text
from .tracks import build_release

AAC_KBPS = 256
# Measured on lofi mixes: 16-bit 44.1 kHz ALAC averages about 720 kbps.
ALAC_KBPS_ESTIMATE = 730
THUMBNAIL_HOST = "i.ytimg.com"
_CODEC_LABELS = {"opus": "OPUS", "mp4a.40.2": "AAC", "mp4a.40.5": "HE-AAC", "vorbis": "VORBIS"}


def codec_label(acodec: str | None) -> str:
    if not acodec or acodec == "none":
        return "UNKNOWN"
    return _CODEC_LABELS.get(acodec, acodec.split(".")[0].upper())


def safe_thumbnail(url: str | None) -> str | None:
    """Only https thumbnails from YouTube's image host reach the page."""
    if not url:
        return None
    parts = urlsplit(url)
    return url if parts.scheme == "https" and parts.hostname == THUMBNAIL_HOST else None


def summarize(info: dict, settings: Settings) -> dict:
    check_playable(info, settings.max_duration_s)
    split = build_release(info, split=True, genre=settings.genre)
    single = build_release(info, split=False, genre=settings.genre)
    duration = float(info["duration"])
    return {
        "id": info.get("id"),
        "title": clean_text(info.get("title")) or "Untitled",
        "channel": split.album_artist if split.is_split else single.tracks[0].artist,
        "year": split.year,
        "duration": duration,
        "thumbnail": safe_thumbnail(info.get("thumbnail")),
        "source": {
            "format_id": info.get("format_id"),
            "codec": codec_label(info.get("acodec")),
            "kbps": round(info.get("abr") or 0),
            "khz": round((info.get("asr") or 0) / 1000, 1),
        },
        "tracks": [
            {"number": t.number, "title": t.title, "artist": t.artist, "start": t.start, "duration": t.duration}
            for t in split.tracks
        ] if split.is_split else [],
        "single": {"title": single.tracks[0].title, "artist": single.tracks[0].artist, "album": single.album},
        "estimate": {
            "aac": int(duration * AAC_KBPS * 1000 / 8),
            "alac": int(duration * ALAC_KBPS_ESTIMATE * 1000 / 8),
        },
    }
