"""ffmpeg encoding for the iPod: 44.1 kHz, 16-bit, AAC 256 or ALAC, in .m4a.

Chain: decode the source, resample to 44.1 kHz (the iPod DAC rate) with a
long swr filter, TPDF-dither to 16-bit, then encode with Apple's AudioToolbox
AAC (constrained VBR 256k, the iTunes Plus spec) or Apple Lossless. A source
that is already AAC-LC at 44.1 kHz is stream-copied in AAC mode, since
re-encoding AAC to AAC only loses quality.
"""

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

SAMPLE_RATE = 44100
AAC_BITRATE = "256k"
RESAMPLE = (
    f"aresample={SAMPLE_RATE}:resampler=swr:filter_size=64:phase_shift=10"
    ":cutoff=0.97:dither_method=triangular"
)


class Mode(str, Enum):
    AAC = "aac"
    ALAC = "alac"


class EncodeError(RuntimeError):
    pass


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class SourceInfo:
    codec: str
    profile: str
    sample_rate: int
    channels: int
    duration: float


def ffmpeg_bin() -> str:
    return _require("ffmpeg")


def ffprobe_bin() -> str:
    return _require("ffprobe")


def _require(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise EncodeError(f"{name} not found on PATH. Install it with: brew install ffmpeg")
    return path


@functools.cache
def aac_encoder() -> str:
    """'aac_at' (Apple AudioToolbox) when this ffmpeg has it, else 'aac'."""
    out = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30
    ).stdout
    return "aac_at" if re.search(r"^\s*A\S*\s+aac_at\s", out, re.MULTILINE) else "aac"


@functools.cache
def ffmpeg_version() -> str:
    out = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-version"], capture_output=True, text=True, timeout=30
    ).stdout
    match = re.match(r"ffmpeg version (\S+)", out)
    return match.group(1) if match else "unknown"


def probe(path: Path) -> SourceInfo:
    out = subprocess.run(
        [
            ffprobe_bin(), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,profile,sample_rate,channels:format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise EncodeError(f"ffprobe could not read {path.name}: {out.stderr.strip()[-300:]}")
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise EncodeError(f"{path.name} has no audio stream")
    stream = streams[0]
    return SourceInfo(
        codec=stream.get("codec_name") or "",
        profile=stream.get("profile") or "",
        sample_rate=int(stream.get("sample_rate") or 0),
        channels=int(stream.get("channels") or 2),
        duration=float((data.get("format") or {}).get("duration") or 0),
    )


def can_passthrough(source: SourceInfo, mode: Mode) -> bool:
    return (
        mode is Mode.AAC
        and source.codec == "aac"
        and source.profile.upper() == "LC"
        and source.sample_rate == SAMPLE_RATE
        and source.channels <= 2
    )


def build_command(
    src: Path,
    dst: Path,
    mode: Mode,
    source: SourceInfo,
    *,
    start: float | None = None,
    duration: float | None = None,
    encoder: str | None = None,
) -> list[str]:
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(src), "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1"]

    if can_passthrough(source, mode):
        cmd += ["-c:a", "copy"]
    else:
        if source.channels > 2:
            cmd += ["-ac", "2"]
        if mode is Mode.ALAC:
            sample_fmt, codec = "s16p", ["-c:a", "alac"]
        elif (encoder or aac_encoder()) == "aac_at":
            sample_fmt = "s16"
            codec = ["-c:a", "aac_at", "-aac_at_mode", "cvbr", "-b:a", AAC_BITRATE]
        else:
            sample_fmt, codec = "fltp", ["-c:a", "aac", "-b:a", AAC_BITRATE]
        cmd += ["-af", f"{RESAMPLE},aformat=sample_fmts={sample_fmt}:sample_rates={SAMPLE_RATE}", *codec]

    cmd += ["-f", "ipod", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(dst)]
    return cmd


class StopFlag(Protocol):
    def is_set(self) -> bool: ...


def run(
    cmd: list[str],
    duration: float,
    on_progress: Callable[[float], None] | None = None,
    cancelled: StopFlag | None = None,
) -> None:
    """Run ffmpeg, reporting 0..1 progress from its -progress output."""
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if cancelled is not None and cancelled.is_set():
                    raise Cancelled()
                key, _, value = line.strip().partition("=")
                if key == "out_time_us" and value.isdigit() and duration > 0 and on_progress:
                    on_progress(min(1.0, int(value) / 1_000_000 / duration))
            proc.wait()
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        if proc.returncode != 0:
            errors.seek(0)
            tail = errors.read().decode("utf-8", errors="replace").strip()[-400:]
            raise EncodeError(f"ffmpeg exited with {proc.returncode}: {tail}")
    if on_progress:
        on_progress(1.0)
