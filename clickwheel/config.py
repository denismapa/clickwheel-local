"""Settings, read once from CLICKWHEEL_* environment variables."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    work_dir: Path = Path(tempfile.gettempdir()) / "clickwheel"
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")
    max_jobs: int = 2
    max_active_jobs: int = 8
    encode_workers: int = 4
    max_duration_min: int = 720
    file_ttl_min: int = 60
    genre: str = "Lo-Fi"
    open_browser: bool = True

    def __post_init__(self) -> None:
        # Without sign-in, the app must not listen beyond this computer.
        open_to_network = self.host not in LOOPBACK_HOSTS
        if open_to_network:
            raise ValueError("Without sign-in Clickwheel only listens on 127.0.0.1 or localhost")

    @property
    def max_duration_s(self) -> int:
        return self.max_duration_min * 60

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        hosts = tuple(h.strip() for h in _env("CLICKWHEEL_ALLOWED_HOSTS").split(",") if h.strip())
        if hosts:  # loopback names always work (health checks, the Mac itself)
            hosts = tuple(dict.fromkeys((*hosts, "127.0.0.1", "localhost")))
        work_dir = _env("CLICKWHEEL_WORK_DIR")
        genre = os.environ.get("CLICKWHEEL_GENRE")
        return cls(
            host=_env("CLICKWHEEL_HOST") or defaults.host,
            port=_int("CLICKWHEEL_PORT", defaults.port),
            work_dir=Path(work_dir).expanduser() if work_dir else defaults.work_dir,
            allowed_hosts=hosts or defaults.allowed_hosts,
            max_jobs=_int("CLICKWHEEL_MAX_JOBS", defaults.max_jobs),
            encode_workers=_int("CLICKWHEEL_ENCODE_WORKERS", min(defaults.encode_workers, os.cpu_count() or 1)),
            max_duration_min=_int("CLICKWHEEL_MAX_DURATION_MIN", defaults.max_duration_min),
            file_ttl_min=_int("CLICKWHEEL_FILE_TTL_MIN", defaults.file_ttl_min),
            genre=defaults.genre if genre is None else genre.strip(),
            open_browser=_bool("CLICKWHEEL_OPEN_BROWSER", defaults.open_browser),
        )
