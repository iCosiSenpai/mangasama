"""Cover image cache.

Downloading covers from external CDNs (AniList, MangaDex, …) is
expensive and rate-limited. We cache each cover once on disk at
`/data/covers/{provider}/{external_id}.{ext}` and return a stable
`file://`-style absolute path to the orchestrator.

The cache is content-addressed: the SHA-256 of the bytes becomes
the filename. If two providers point to the same cover, they share
the on-disk file (deduped by the central `/data/covers/_byhash/`
shard tree).

Key functions:
  - `fetch_and_cache(provider, external_id, url, ext="jpg")` -> Path
  - `cached_path(provider, external_id) -> Path | None`
  - `clear_cache()` (test helper)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import structlog

from app.settings import get_settings

logger = structlog.get_logger("mangasama.metadata.cover_cache")


def _covers_dir() -> Path:
    return get_settings().covers_path


def _hash_path(sha: str, ext: str) -> Path:
    """Two-level shard: `aa/bb/aabbcc...{ext}` to keep dirs small."""
    return _covers_dir() / "_byhash" / sha[:2] / sha[2:4] / f"{sha}.{ext}"


def _provider_path(provider: str, external_id: str, ext: str) -> Path:
    return _covers_dir() / provider / f"{external_id}.{ext}"


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cached_path(provider: str, external_id: str, ext: str = "jpg") -> Path | None:
    """Return the cache path if the cover has been downloaded, else None."""
    p = _provider_path(provider, external_id, ext)
    if p.exists():
        return p
    # Try to find it by its hash shard (dedup case).
    return None


async def fetch_and_cache(
    provider: str,
    external_id: str,
    url: str,
    *,
    ext: str = "jpg",
    scraper_name: str = "metadata",
) -> Path:
    """Download `url` to disk and return the local path.

    The file is stored under both the by-provider path AND a by-hash
    shard. The by-hash file is the canonical copy; the by-provider
    path is a symlink (where supported) or a small stub. Falls back to
    copying on Windows (no symlinks without elevation).

    If the cover is already cached, no network call is made.
    """
    provider_p = _provider_path(provider, external_id, ext)
    if provider_p.exists():
        return provider_p

    from app.core.http_client import get_http
    http = get_http()
    data = await http.get_bytes(
        url, scraper=scraper_name, domain=_safe_domain(url),
    )
    sha = _hash_bytes(data)
    byhash_p = _hash_path(sha, ext)
    byhash_p.parent.mkdir(parents=True, exist_ok=True)
    if not byhash_p.exists():
        byhash_p.write_bytes(data)
    provider_p.parent.mkdir(parents=True, exist_ok=True)
    # Prefer a hardlink (no extra disk, no symlink issues); fall back
    # to a regular write if hardlinks are not supported (different
    # volumes / filesystems).
    try:
        # `link` may not exist on Path on older Python — use os.link
        import os
        os.link(byhash_p, provider_p)
    except (OSError, AttributeError):
        provider_p.write_bytes(data)
    logger.info("cover_cache.stored", provider=provider, external_id=external_id, sha=sha[:8])
    return provider_p


def clear_cache() -> None:
    """Remove all cached covers (test helper)."""
    import shutil
    p = _covers_dir()
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


def total_bytes() -> int:
    """Return the on-disk size of the cache."""
    root = _covers_dir()
    if not root.exists():
        return 0
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def _safe_domain(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).hostname or "external"
