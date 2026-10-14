"""Cover art: a YouTube thumbnail becomes a 600 px square baseline JPEG.

iPods display square art and some models skip progressive JPEGs, so the
thumbnail is center-cropped, scaled with lanczos and written by ffmpeg's
baseline mjpeg encoder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .audio import ffmpeg_bin

COVER_SIZE = 600


def make_cover(src: Path, dst: Path, size: int = COVER_SIZE) -> Path:
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", f"crop='min(iw,ih)':'min(iw,ih)',scale={size}:{size}:flags=lanczos,format=yuvj420p",
        "-frames:v", "1", "-update", "1", "-q:v", "2", "-c:v", "mjpeg", "-f", "image2",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    return dst


def is_baseline_jpeg(data: bytes) -> bool:
    """True for a baseline (SOF0) JPEG, False for progressive (SOF2) or non-JPEG."""
    if not data.startswith(b"\xff\xd8"):
        return False
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return False
        marker = data[i + 1]
        if marker == 0xC0:
            return True
        if marker == 0xC2:
            return False
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        i += 2 + length
    return False
