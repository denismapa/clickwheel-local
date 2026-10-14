"""One job in three sectors: FETCH (yt-dlp), ENCODE (ffmpeg per track), PACK (tags, zip)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import artwork, audio, source, tagging
from .audio import Cancelled
from .config import Settings
from .textutil import safe_filename
from .tracks import Release, Track, build_release

if TYPE_CHECKING:
    from .jobs import Job

log = logging.getLogger("clickwheel.pipeline")

FETCH, ENCODE, PACK = 0, 1, 2


@dataclass(frozen=True)
class Result:
    path: Path
    filename: str
    size: int
    tracks: int


def track_filename(release: Release, track: Track) -> str:
    name = safe_filename(f"{track.artist} - {track.title}")
    if not release.is_split:
        return f"{name}.m4a"
    width = max(2, len(str(len(release.tracks))))
    return f"{track.number:0{width}d} {name}.m4a"


def run(job: Job, settings: Settings, fetcher=source.fetch) -> Result:
    job.report(FETCH, 0.0, "Reading source")
    download = fetcher(job.url, job.dir / "src", job.fetch_progress, job.cancelled)
    source.check_playable(download.info, settings.max_duration_s)
    release = build_release(download.info, split=job.split, genre=settings.genre)
    job.set_title(release.album)
    job.report(FETCH, 1.0, "Source in")

    cover = _cover(download.thumbnail, job.dir / "cover.jpg")
    source_info = audio.probe(download.audio)
    files = _encode(job, release, download.audio, source_info, settings.encode_workers)
    shutil.rmtree(job.dir / "src", ignore_errors=True)
    return _pack(job, release, files, cover)


def _cover(thumbnail: Path | None, dst: Path) -> bytes | None:
    if thumbnail is None:
        return None
    try:
        return artwork.make_cover(thumbnail, dst).read_bytes()
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("cover art skipped: %s", exc)
        return None


class _AnySet:
    """A stop flag that trips when the job is cancelled or a sibling track failed."""

    def __init__(self, *events: threading.Event):
        self._events = events

    def is_set(self) -> bool:
        return any(event.is_set() for event in self._events)


def _encode(job: Job, release: Release, src: Path, source_info, workers: int) -> list[Path]:
    out_dir = job.dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = len(release.tracks)
    total = release.duration or 1.0
    encoded = {t.number: 0.0 for t in release.tracks}
    lock = threading.Lock()
    failed = threading.Event()
    stop = _AnySet(job.cancelled, failed)

    def encode_one(track: Track) -> Path:
        if stop.is_set():
            raise Cancelled()
        dst = out_dir / track_filename(release, track)
        label = f"Track {track.number}/{count} · {track.artist} - {track.title}" if release.is_split else track.title

        def progress(fraction: float) -> None:
            with lock:
                encoded[track.number] = fraction * track.duration
                overall = sum(encoded.values()) / total
            job.report(ENCODE, overall, label)

        segment = {"start": track.start, "duration": track.duration} if release.is_split else {}
        cmd = audio.build_command(src, dst, job.mode, source_info, **segment)
        try:
            audio.run(cmd, track.duration, progress, stop)
        except Cancelled:
            raise
        except BaseException:
            failed.set()
            raise
        return dst

    with ThreadPoolExecutor(max_workers=max(1, min(workers, count)), thread_name_prefix="encode") as pool:
        futures = [pool.submit(encode_one, t) for t in release.tracks]
    errors = [f.exception() for f in futures]
    real = next((e for e in errors if e is not None and not isinstance(e, Cancelled)), None)
    if real is not None:
        raise real
    if job.cancelled.is_set() or any(errors):
        raise Cancelled()
    return [f.result() for f in futures]


def _pack(job: Job, release: Release, files: list[Path], cover: bytes | None) -> Result:
    count = len(files)
    steps = count + (1 if release.is_split else 0)
    for done, (track, path) in enumerate(zip(release.tracks, files), start=1):
        if job.cancelled.is_set():
            raise Cancelled()
        tagging.write_tags(path, release, track, cover)
        job.report(PACK, done / steps, f"Tagging {done}/{count}")

    if release.is_split:
        folder = safe_filename(release.album, fallback="YouTube mix")
        final = job.dir / f"{folder}.zip"
        job.report(PACK, count / steps, "Packing zip")
        with zipfile.ZipFile(final, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in files:
                if job.cancelled.is_set():
                    raise Cancelled()
                archive.write(path, f"{folder}/{path.name}")
        shutil.rmtree(job.dir / "out", ignore_errors=True)
    else:
        final = files[0]

    job.report(PACK, 1.0, "Ready")
    return Result(path=final, filename=final.name, size=final.stat().st_size, tracks=count)
