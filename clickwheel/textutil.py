"""Text cleanup for iPod tags and filenames, plus time formatting.

iPod fonts have no emoji, and lofi titles are full of them (and of fullwidth
letters like "Ｎｉｇｈｔ"). NFKC folds the fullwidth forms to plain text; the
character filter drops pictographs, joiners and variation selectors.
"""

from __future__ import annotations

import re
import unicodedata

# Symbols (emoji, dingbats), format chars (ZWJ, tags), controls, surrogates,
# private use, unassigned, enclosing marks (keycaps).
_DROP_CATEGORIES = frozenset({"So", "Cf", "Cc", "Cs", "Co", "Cn", "Me"})
_DROP_RANGES = (
    (0xFE00, 0xFE0F),  # variation selectors
    (0xE0100, 0xE01EF),  # variation selectors supplement
    (0x1F3FB, 0x1F3FF),  # skin-tone modifiers
)
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]|\{\s*\}|【\s*】|「\s*」")
_SPACES = re.compile(r"\s+")
_EDGE_JUNK = " -–—|·•~:,"
_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]')


def _keep(ch: str) -> bool:
    cp = ord(ch)
    if any(lo <= cp <= hi for lo, hi in _DROP_RANGES):
        return False
    return unicodedata.category(ch) not in _DROP_CATEGORIES


def clean_text(value: str | None) -> str:
    """Normalize a title for iPod display: NFKC, no emoji, single spaces."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = "".join(ch if _keep(ch) else (" " if ch in "\t\r\n" else "") for ch in text)
    text = _EMPTY_BRACKETS.sub(" ", text)
    return _SPACES.sub(" ", text).strip(_EDGE_JUNK)


def safe_filename(value: str | None, fallback: str = "track", max_bytes: int = 120) -> str:
    """A filename that works on macOS, Windows and inside zips."""
    text = _UNSAFE_FILENAME.sub(" ", clean_text(value))
    text = _SPACES.sub(" ", text).strip(" .")
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        text = encoded[:max_bytes].decode("utf-8", errors="ignore").strip(" .")
    return text or fallback


def format_duration(seconds: float | None) -> str:
    """1:44:52 or 3:07."""
    total = max(0, int(round(seconds or 0)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
