"""Job registry: a small worker pool, progress snapshots, cancel, cleanup."""

from __future__ import annotations

import logging
import re
import secrets
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from functools import partial
from pathlib import Path

from . import pipeline
from .audio import Cancelled, EncodeError, Mode
from .config import Settings
from .pipeline import Result
from .source import FetchProgress, SourceError

log = logging.getLogger("clickwheel.jobs")

JOB_ID = re.compile(r"^[0-9a-f]{32}$")


class State(str, Enum):
    QUEUED = "queued"
    FETCH = "fetch"
    ENCODE = "encode"
    PACK = "pack"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


SECTOR_STATES = (State.FETCH, State.ENCODE, State.PACK)
FINISHED = frozenset({State.DONE, State.ERROR, State.CANCELLED})


class QueueFull(Exception):
    pass


class Job:
    def __init__(self, url: str, mode: Mode, split: bool, root: Path):
        self.id = secrets.token_hex(16)
        self.url = url
        self.mode = mode
        self.split = split
        self.dir = root / self.id
        self.created = time.time()
        self.finished_at: float | None = None
        self.state = State.QUEUED
        self.sectors = [0.0, 0.0, 0.0]
        self.detail = "Queued"
        self.title = ""
        self.speed: float | None = None
        self.eta: float | None = None
        self.error: dict | None = None
        self.result: Result | None = None
        self.cancelled = threading.Event()
        self._lock = threading.Lock()

    # Called from worker threads by the pipeline.
    def report(self, sector: int, fraction: float, detail: str | None = None) -> None:
        with self._lock:
            if self.state in FINISHED:
                return
            self.state = SECTOR_STATES[sector]
            for done in range(sector):
                self.sectors[done] = 1.0
            self.sectors[sector] = max(self.sectors[sector], min(1.0, max(0.0, fraction)))
            if detail:
                self.detail = detail
            if sector != pipeline.FETCH:
                self.speed = self.eta = None

    def fetch_progress(self, progress: FetchProgress) -> None:
        self.report(pipeline.FETCH, progress.fraction, progress.note or "Downloading source")
        with self._lock:
            self.speed, self.eta = progress.speed, progress.eta

    def set_title(self, title: str) -> None:
        with self._lock:
            self.title = title

    def finish(self, result: Result) -> None:
        with self._lock:
            self.state, self.result, self.sectors = State.DONE, result, [1.0, 1.0, 1.0]
            self.detail, self.finished_at = "Ready", time.time()

    def fail(self, title: str, message: str, detail: str = "") -> None:
        with self._lock:
            self.state, self.finished_at = State.ERROR, time.time()
            self.error = {"title": title, "message": message, "detail": detail}

    def mark_cancelled(self) -> None:
        with self._lock:
            if self.state not in FINISHED:
                self.state, self.finished_at, self.detail = State.CANCELLED, time.time(), "Cancelled"

    @property
    def is_finished(self) -> bool:
        return self.state in FINISHED

    def snapshot(self) -> dict:
        with self._lock:
            result = None
            if self.result is not None:
                result = {"filename": self.result.filename, "size": self.result.size, "tracks": self.result.tracks}
            return {
                "id": self.id,
                "url": self.url,
                "mode": self.mode.value,
                "split": self.split,
                "state": self.state.value,
                "title": self.title,
                "sectors": [round(s, 4) for s in self.sectors],
                "progress": round(sum(self.sectors) / 3, 4),
                "detail": self.detail,
                "speed": self.speed,
                "eta": self.eta,
                "error": self.error,
                "result": result,
                "created": self.created,
            }


class JobManager:
    def __init__(self, settings: Settings, runner: Callable[[Job], Result] | None = None):
        self.settings = settings
        self.root = settings.work_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._purge_stale()
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=settings.max_jobs, thread_name_prefix="job")
        self._runner = runner or (lambda job: pipeline.run(job, settings))

    def submit(self, url: str, mode: Mode, split: bool) -> Job:
        self.sweep()
        with self._lock:
            active = sum(1 for job in self._jobs.values() if not job.is_finished)
            if active >= self.settings.max_active_jobs:
                raise QueueFull()
            job = Job(url, mode, split, self.root)
            self._jobs[job.id] = job
        self._pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job | None:
        self.sweep()
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self) -> list[Job]:
        self.sweep()
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created, reverse=True)

    def cancel(self, job_id: str) -> Job | None:
        """Stop a running job, or discard a finished one and its files."""
        job = self.get(job_id)
        if job is None:
            return None
        job.cancelled.set()
        if job.state is State.QUEUED:
            job.mark_cancelled()
        elif job.is_finished:
            with self._lock:
                self._jobs.pop(job.id, None)
            shutil.rmtree(job.dir, ignore_errors=True)
        return job

    def sweep(self) -> None:
        """Delete finished jobs older than the file TTL."""
        cutoff = time.time() - self.settings.file_ttl_min * 60
        with self._lock:
            expired = [j for j in self._jobs.values() if j.finished_at and j.finished_at < cutoff]
            for job in expired:
                self._jobs.pop(job.id, None)
        for job in expired:
            shutil.rmtree(job.dir, ignore_errors=True)

    def shutdown(self) -> None:
        with self._lock:
            jobs = list(self._jobs.values())
        for job in jobs:
            job.cancelled.set()
        self._pool.shutdown(wait=True, cancel_futures=True)
        for job in jobs:
            shutil.rmtree(job.dir, ignore_errors=True)

    def _run(self, job: Job) -> None:
        if job.cancelled.is_set():
            job.mark_cancelled()
            return
        job.dir.mkdir(parents=True, exist_ok=True)
        # Files go first, then the final state: a client that sees "cancelled"
        # or "error" never finds leftovers.
        try:
            result = self._runner(job)
        except Cancelled:
            outcome = job.mark_cancelled
        except SourceError as exc:
            outcome = partial(job.fail, exc.title, exc.message, exc.detail)
        except EncodeError as exc:
            # ffmpeg errors quote file paths; keep server paths out of the page.
            detail = str(exc).replace(str(job.dir), "<job>").replace(str(self.root), "<work>")
            outcome = partial(job.fail, "ENCODE FAILED.", "ffmpeg stopped before the end.", detail)
        except Exception:
            log.exception("job %s failed", job.id)
            outcome = partial(job.fail, "JOB FAILED.", "Unexpected error. The server log has the trace.")
        else:
            if not job.cancelled.is_set():
                job.finish(result)
                log.info("job %s done: %s (%d tracks, %d bytes)", job.id, result.filename, result.tracks, result.size)
                return
            outcome = job.mark_cancelled
        shutil.rmtree(job.dir, ignore_errors=True)
        outcome()

    def _purge_stale(self) -> None:
        """Remove job folders left by a previous run; touch nothing else."""
        for path in self.root.iterdir():
            if path.is_dir() and JOB_ID.match(path.name):
                shutil.rmtree(path, ignore_errors=True)
