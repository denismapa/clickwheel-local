"""Turn yt-dlp metadata into an iPod release: album fields plus a track list.

Lofi mixes carry chapters titled "Artist - Title" (or with an en dash); each
chapter becomes a track. Without chapters, or with splitting off, the whole
video is one track.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .textutil import clean_text

MIN_TRACK_SECONDS = 1.0
INTRO_TITLE = "Intro"

_LEADING_NUMBER = re.compile(
    r"^(?:\d{1,3}[.):](?=\s)|\[\s*\d{1,3}\s*\]|\(\s*\d{1,3}\s*\)|#\d{1,3}\b|\d{1,3}\s+[-–—|](?=\s))\s*"
)
_TIMESTAMP = r"[\[(]?\d{1,2}:\d{2}(?::\d{2})?[\])]?"
_LEADING_TIME = re.compile(rf"^{_TIMESTAMP}\s*[-–—|]?\s*")
_TRAILING_TIME = re.compile(rf"\s*[-–—|]?\s*{_TIMESTAMP}$")
_ARTIST_SPLIT = re.compile(r"\s+[-–—]\s+")
_TOPIC_SUFFIX = re.compile(r"\s+-\s+Topic$")
_QUOTES = "\"'“”‘’"


@dataclass(frozen=True)
class Track:
    number: int
    start: float
    end: float
    title: str
    artist: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class Release:
    album: str
    album_artist: str
    year: str | None
    genre: str
    source_url: str
    tracks: tuple[Track, ...]
    compilation: bool = False
    gapless: bool = False

    @property
    def is_split(self) -> bool:
        return len(self.tracks) > 1

    @property
    def duration(self) -> float:
        return sum(t.duration for t in self.tracks)


def parse_artist_title(text: str | None, default_artist: str) -> tuple[str, str]:
    """'03. Noji – Exhale (1:02:03)' -> ('Noji', 'Exhale')."""
    cleaned = clean_text(text)
    cleaned = _LEADING_TIME.sub("", cleaned)
    cleaned = _TRAILING_TIME.sub("", cleaned)
    cleaned = _LEADING_NUMBER.sub("", cleaned).strip()
    parts = _ARTIST_SPLIT.split(cleaned, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip(_QUOTES + " "):
        return parts[0].strip(), parts[1].strip(_QUOTES + " ")
    return default_artist, cleaned.strip(_QUOTES + " ") or "Untitled"


def channel_name(info: dict) -> str:
    raw = info.get("channel") or info.get("uploader") or info.get("creator") or "YouTube"
    return _TOPIC_SUFFIX.sub("", clean_text(raw)) or "YouTube"


def release_year(info: dict) -> str | None:
    year = info.get("release_year")
    if year:
        return str(year)
    upload = str(info.get("upload_date") or "")
    return upload[:4] if len(upload) >= 4 and upload[:4].isdigit() else None


def _chapter_tracks(chapters: list[dict], duration: float, channel: str) -> list[Track]:
    spans: list[tuple[float, float, str]] = []
    for chapter in sorted(chapters, key=lambda c: float(c.get("start_time") or 0)):
        start = min(max(float(chapter.get("start_time") or 0), 0.0), duration)
        end = min(float(chapter.get("end_time") or duration), duration)
        if end - start >= MIN_TRACK_SECONDS:
            spans.append((start, end, chapter.get("title") or ""))
    if spans and spans[0][0] >= MIN_TRACK_SECONDS:
        spans.insert(0, (0.0, spans[0][0], INTRO_TITLE))
    tracks = []
    for number, (start, end, title) in enumerate(spans, start=1):
        artist, name = parse_artist_title(title, channel)
        tracks.append(Track(number, start, end, name, artist))
    return tracks


def _single_track(info: dict, duration: float, channel: str) -> tuple[Track, str]:
    """One track for the whole video; returns it with the album name."""
    artists = info.get("artists") or ([info["artist"]] if info.get("artist") else [])
    if info.get("track") and artists:
        title = clean_text(info["track"]) or "Untitled"
        artist = clean_text(", ".join(artists)) or channel
        album = clean_text(info.get("album")) or title
        return Track(1, 0.0, duration, title, artist), album
    artist, title = parse_artist_title(info.get("title"), channel)
    return Track(1, 0.0, duration, title, artist), title


def build_release(info: dict, *, split: bool, genre: str) -> Release:
    duration = float(info.get("duration") or 0)
    channel = channel_name(info)
    common = {
        "year": release_year(info),
        "genre": genre,
        "source_url": info.get("webpage_url") or info.get("original_url") or "",
    }
    if split:
        tracks = _chapter_tracks(info.get("chapters") or [], duration, channel)
        if len(tracks) >= 2:
            return Release(
                album=clean_text(info.get("title")) or "YouTube mix",
                album_artist=channel,
                tracks=tuple(tracks),
                compilation=any(t.artist != channel for t in tracks),
                gapless=True,
                **common,
            )
    track, album = _single_track(info, duration, channel)
    return Release(album=album, album_artist=track.artist, tracks=(track,), **common)
