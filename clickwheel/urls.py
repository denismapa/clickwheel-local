"""YouTube URL validation.

Every link is reduced to https://www.youtube.com/watch?v=<11-char id> before
yt-dlp sees it, so nothing but a YouTube video page can ever be fetched.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

MAX_URL_LENGTH = 2048
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_WATCH_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
)
_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
_PATH_PREFIXES = ("shorts", "live", "embed", "v", "e")


class UrlError(ValueError):
    """The text is not a single YouTube video link."""

    def __init__(self, title: str, message: str):
        super().__init__(f"{title} {message}")
        self.title = title
        self.message = message


NOT_YOUTUBE = UrlError("NOT A YOUTUBE LINK.", "Paste a youtube.com or youtu.be address.")
NO_VIDEO = UrlError("NO VIDEO IN LINK.", "Paste the link of one video or mix.")
PLAYLIST = UrlError("PLAYLIST LINK.", "Playlists are not supported yet. Paste one video or mix.")


def video_id(raw: str) -> str:
    """Return the 11-character video id, or raise UrlError."""
    text = (raw or "").strip()
    if not text or len(text) > MAX_URL_LENGTH:
        raise NOT_YOUTUBE
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
    except ValueError as exc:
        raise NOT_YOUTUBE from exc
    if parts.scheme not in {"http", "https"} or "@" in parts.netloc:  # no user:pass@ tricks
        raise NOT_YOUTUBE

    segments = [s for s in parts.path.split("/") if s]
    if host in _SHORT_HOSTS:
        candidate = segments[0] if segments else ""
    elif host in _WATCH_HOSTS:
        query = parse_qs(parts.query)
        if segments[:1] == ["watch"]:
            candidate = (query.get("v") or [""])[0]
        elif len(segments) >= 2 and segments[0] in _PATH_PREFIXES:
            candidate = segments[1]
        elif segments[:1] == ["playlist"] or "list" in query:
            raise PLAYLIST
        else:
            raise NO_VIDEO
    else:
        raise NOT_YOUTUBE

    if not _VIDEO_ID.match(candidate):
        raise NO_VIDEO
    return candidate


def canonical_url(raw: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id(raw)}"
