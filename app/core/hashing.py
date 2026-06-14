"""SHA-256 helpers for content addressing."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    """Return hex SHA-256 of a bytes object."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, *, chunk_size: int = 1 << 16) -> str:
    """Stream a file and return its hex SHA-256.

    Uses a 64 KB chunk size — same as Git. Memory-safe for multi-GB files.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
