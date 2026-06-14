"""Cover cache tests.

We use `tmp_path` for the cache root (autouse `_env` fixture in
`conftest.py` points the app at a temp DATA_DIR). The cache is keyed
on `provider + external_id`; the by-hash shard is a dedup layer.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
import respx

from app.core.http_client import get_http
from app.metadata.cover_cache import (
    _covers_dir,
    cached_path,
    clear_cache,
    fetch_and_cache,
    total_bytes,
)

SAMPLE_JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"hello world" * 100


@pytest.fixture(autouse=True)
def _clean_cache():
    """Wipe the cache before each test to keep results deterministic."""
    clear_cache()
    yield
    clear_cache()


# -------------------------------------------------------------- fetch


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_stores_cover() -> None:
    url = "https://example.com/cover.jpg"
    respx.get(url).mock(return_value=httpx.Response(200, content=SAMPLE_JPG))
    p = await fetch_and_cache("anilist", "1", url)
    assert p.exists()
    assert p.read_bytes() == SAMPLE_JPG
    # The by-hash shard also exists.
    expected = _covers_dir() / "_byhash"
    assert any(expected.rglob("*.jpg"))


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_uses_provider_path() -> None:
    url = "https://example.com/c2.jpg"
    respx.get(url).mock(return_value=httpx.Response(200, content=SAMPLE_JPG))
    p = await fetch_and_cache("mangadex", "abc-123", url)
    assert p.parent.name == "mangadex"
    assert p.name == "abc-123.jpg"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_dedupes_by_hash() -> None:
    """Same bytes, different provider+id, only one file on disk."""
    url_a = "https://example.com/a.jpg"
    url_b = "https://example.com/b.jpg"
    respx.get(url_a).mock(return_value=httpx.Response(200, content=SAMPLE_JPG))
    respx.get(url_b).mock(return_value=httpx.Response(200, content=SAMPLE_JPG))

    p1 = await fetch_and_cache("anilist", "1", url_a)
    p2 = await fetch_and_cache("mangadex", "abc", url_b)
    assert p1.exists() and p2.exists()
    # Two provider paths but one by-hash file.
    hash_shards = list((_covers_dir() / "_byhash").rglob("*.jpg"))
    assert len(hash_shards) == 1


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_no_network_when_cached() -> None:
    url = "https://example.com/cached.jpg"
    route = respx.get(url).mock(return_value=httpx.Response(200, content=SAMPLE_JPG))
    p1 = await fetch_and_cache("anilist", "x", url)
    assert route.call_count == 1
    p2 = await fetch_and_cache("anilist", "x", url)
    assert route.call_count == 1   # not called again
    assert p1 == p2


# --------------------------------------------------------- cached_path


def test_cached_path_returns_none_when_missing(tmp_path: Path) -> None:
    assert cached_path("anilist", "missing-id") is None


@pytest.mark.asyncio
@respx.mock
async def test_cached_path_returns_path_after_fetch() -> None:
    url = "https://example.com/cp.jpg"
    respx.get(url).mock(return_value=httpx.Response(200, content=SAMPLE_JPG))
    await fetch_and_cache("anilist", "abc", url)
    p = cached_path("anilist", "abc")
    assert p is not None
    assert p.exists()


# ----------------------------------------------------------- total_bytes


@pytest.mark.asyncio
@respx.mock
async def test_total_bytes_reflects_cache_size() -> None:
    assert total_bytes() == 0
    url = "https://example.com/big.jpg"
    payload = SAMPLE_JPG * 5   # 5KB-ish
    respx.get(url).mock(return_value=httpx.Response(200, content=payload))
    await fetch_and_cache("anilist", "big", url)
    assert total_bytes() > 0


# ----------------------------------------------------- hardlink behavior


@pytest.mark.asyncio
@respx.mock
async def test_provider_path_is_hardlinked_to_byhash() -> None:
    """If hardlinks work, the provider path shares the same inode."""
    url = "https://example.com/hl.jpg"
    respx.get(url).mock(return_value=httpx.Response(200, content=SAMPLE_JPG))
    p = await fetch_and_cache("anilist", "h1", url)
    # Find the by-hash shard.
    shard = next((_covers_dir() / "_byhash").rglob("*.jpg"))
    # Inode check (works on both Windows + Unix when hardlinks succeed).
    # On Windows we accept either: same inode, OR same content.
    if hasattr(os, "stat") and hasattr(os, "link"):
        try:
            assert p.stat().st_ino == shard.stat().st_ino
        except (OSError, ValueError):
            # If the FS doesn't support hardlinks, fall back to content equality.
            assert p.read_bytes() == shard.read_bytes()
    else:
        assert p.read_bytes() == shard.read_bytes()
