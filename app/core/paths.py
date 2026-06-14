"""Path and filename helpers for safe on-disk storage."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Filesystem-unsafe characters: \ / : * ? " < > | plus control chars.
_UNSAFE_RE = re.compile(r'[\\/:\*\?"<>\|\x00-\x1f]')
# Reserved Windows names.
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
# Collapse multiple spaces / dots.
_WHITESPACE_RE = re.compile(r"\s+")
_DOTS_RE = re.compile(r"\.{2,}")


def safe_filename(name: str, *, max_length: int = 200) -> str:
    """Make a string safe for use as a filename on all major filesystems.

    - Replaces unsafe characters with `_`
    - Strips leading/trailing whitespace and dots
    - Collapses runs of whitespace to a single space
    - Avoids Windows reserved names (CON, PRN, COM1, ...)
    - Truncates to `max_length` (UTF-8 safe via `unicodedata.normalize`)
    - Returns a non-empty string (falls back to `"untitled"`)

    Used for series titles, chapter titles, volume numbers in folder/file names.
    """
    if not name:
        return "untitled"

    # Normalise Unicode (NFC) so the same visual string always hashes the same.
    s = unicodedata.normalize("NFC", name).strip()
    s = _UNSAFE_RE.sub("_", s)
    s = _WHITESPACE_RE.sub(" ", s)
    s = _DOTS_RE.sub(".", s)
    s = s.strip(" ._")

    if not s:
        return "untitled"

    # Avoid Windows reserved names.
    if s.upper() in _WIN_RESERVED or s.split(".", 1)[0].upper() in _WIN_RESERVED:
        s = "_" + s

    # Truncate by characters (acceptable for our use; filesystem limit is bytes).
    if len(s) > max_length:
        s = s[:max_length].rstrip(" ._")

    return s or "untitled"


def chapter_filename(
    series_title: str,
    chapter_number: str,
    chapter_title: str | None = None,
    *,
    language: str | None = None,
    extension: str = "cbz",
) -> str:
    """Build a chapter CBZ filename like `Series Title - ch001 - title (it).cbz`.

    Note: this is the *single* chapter filename; the folder structure is the
    job of `app/services/folder_strategy.py`.
    """
    parts = [safe_filename(series_title), f"ch{_pad(chapter_number)}"]
    if chapter_title:
        parts.append(safe_filename(chapter_title))
    base = " - ".join(parts)
    if language:
        base += f" ({language})"
    return f"{base}.{extension}"


def _pad(num: str) -> str:
    """Zero-pad a chapter number, but keep decimals readable.

    `1` -> `001`, `1.5` -> `001.5`, `10` -> `010`, `100` -> `100`,
    `S1` -> `S1` (special), `0` -> `000`.
    """
    s = str(num).strip()
    if not s:
        return "000"
    # Split into integer + decimal parts.
    if "." in s:
        int_part, _, dec = s.partition(".")
        try:
            return f"{int(int_part):03d}.{dec}"
        except ValueError:
            return s
    try:
        return f"{int(s):03d}"
    except ValueError:
        return s  # leave alphabetic chapter IDs as-is


def volume_folder_name(volume_number: str | int | None) -> str:
    """Format a volume as a folder name: `Volume 001`, `Vol 1.5`, etc."""
    n = "" if volume_number is None else str(volume_number)
    return f"Volume {_pad(n)}" if n else "Volume 000"


def ensure_dir(path: Path) -> Path:
    """mkdir -p; return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path
