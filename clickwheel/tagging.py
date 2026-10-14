"""iPod tags and cover art for .m4a files, written with mutagen."""

from __future__ import annotations

from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover

from . import __version__
from .tracks import Release, Track

MEDIA_KIND_MUSIC = 1


def write_tags(path: Path, release: Release, track: Track, cover: bytes | None = None) -> None:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags["\xa9nam"] = [track.title]
    tags["\xa9ART"] = [track.artist]
    tags["aART"] = [release.album_artist]
    tags["\xa9alb"] = [release.album]
    tags["trkn"] = [(track.number, len(release.tracks))]
    tags["disk"] = [(1, 1)]
    tags["stik"] = [MEDIA_KIND_MUSIC]
    tags["\xa9too"] = [f"Clickwheel {__version__}"]
    if release.year:
        tags["\xa9day"] = [release.year]
    if release.genre:
        tags["\xa9gen"] = [release.genre]
    if release.source_url:
        tags["\xa9cmt"] = [release.source_url]
    if release.compilation:
        tags["cpil"] = True
    if release.gapless:
        tags["pgap"] = True
    if cover:
        tags["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()
