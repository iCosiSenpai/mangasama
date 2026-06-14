"""Tests for the domain health cron (`app/services/health.py`) + auto-fallback."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
from sqlalchemy import select

from app.db.session import session_scope
from app.models.orm import DomainHealth
from app.scrapers.domain_registry import DomainRegistry
from app.services import health
from app.settings import get_settings


@pytest.fixture(autouse=True)
def _install_sources_yaml():
    """The per-test temp CONFIG_DIR has no sources.yaml; copy the real one
    in so `DomainRegistry` can resolve domains."""
    src = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"
    dst = get_settings().config_dir / "sources.yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    yield


class FakeClient:
    """Stands in for `httpx.AsyncClient`: 200 for every host except those
    in `fail_domains`, which raise a connection error."""

    def __init__(self, fail_domains: set[str]):
        self.fail = set(fail_domains)

    async def get(self, url: str) -> httpx.Response:
        host = urlparse(url).hostname or ""
        req = httpx.Request("GET", url)
        if host in self.fail:
            raise httpx.ConnectError("down", request=req)
        return httpx.Response(200, request=req)

    async def aclose(self) -> None:
        pass


def _patch_client(monkeypatch, fail_domains: set[str]) -> None:
    monkeypatch.setattr(health, "make_health_client", lambda: FakeClient(fail_domains))


@pytest.mark.asyncio
async def test_health_flips_domain_after_three_failures(monkeypatch):
    _patch_client(monkeypatch, {"mangaworld.mx"})

    for _ in range(3):
        result = await health.check_all_domains()
    assert result["checked"] > 0

    async with session_scope() as s:
        rows = {
            (r.source, r.domain): r
            for r in (await s.execute(select(DomainHealth))).scalars().all()
        }
    bad = rows[("mangaworld", "mangaworld.mx")]
    assert bad.healthy is False
    assert bad.fail_count >= 3
    good = rows[("mangaworld", "mangaworldacg.com")]
    assert good.healthy is True
    assert good.fail_count == 0


@pytest.mark.asyncio
async def test_pick_domain_falls_back_to_healthy_alternate(monkeypatch):
    _patch_client(monkeypatch, {"mangaworld.mx"})
    for _ in range(3):
        await health.check_all_domains()

    picked = await DomainRegistry().pick_domain("mangaworld")
    assert picked == "mangaworldacg.com"


@pytest.mark.asyncio
async def test_healthy_domain_recovers_fail_count(monkeypatch):
    # Fail twice, then succeed → fail_count resets, stays healthy.
    _patch_client(monkeypatch, {"api.mangadex.org"})
    await health.check_all_domains()
    await health.check_all_domains()
    _patch_client(monkeypatch, set())
    await health.check_all_domains()

    async with session_scope() as s:
        row = (await s.execute(
            select(DomainHealth).where(DomainHealth.source == "mangadex")
        )).scalars().first()
    assert row.healthy is True
    assert row.fail_count == 0
