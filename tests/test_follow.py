"""Tests for the follow orchestrator (`app/services/follow.py`)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db.session import session_scope
from app.models.orm import (
    Chapter,
    FollowLog,
    Library,
    Series,
    SeriesExternalId,
    Volume,
)
from app.scrapers.base import ScrapedChapter
from app.services import follow


def _sc(eid: str, number: str, language: str = "it") -> ScrapedChapter:
    return ScrapedChapter(
        source="mangadex", external_id=eid, url=f"https://x/{eid}",
        number=number, title=None, language=language, volume_number="1",
    )


async def _make_series() -> int:
    async with session_scope() as s:
        lib = Library(
            name="FollowTest", type="manga", root_path="/tmp/follow",
            folder_strategy="series_volume_chapter", providers=["mangadex"],
            italian_priority=True,
        )
        s.add(lib)
        await s.flush()
        series = Series(
            library_id=lib.id, title="One Piece", sort_title="One Piece", language="it",
        )
        s.add(series)
        await s.flush()
        s.add(SeriesExternalId(
            series_id=series.id, provider="mangadex", external_id="md1",
        ))
        return series.id


def _patch_chapters(monkeypatch, chapters: list[ScrapedChapter]) -> None:
    from app.scrapers import mangadex as md_module

    async def fake(self, external_id, *, language=None, limit=500, offset=0):
        return list(chapters)

    monkeypatch.setattr(md_module.MangaDexScraper, "get_chapters", fake)


@pytest.mark.asyncio
async def test_check_series_enqueues_missing(monkeypatch):
    collected: list = []
    monkeypatch.setattr(follow, "enqueue_download", lambda t: collected.append(t))
    _patch_chapters(monkeypatch, [_sc("md-ch1", "1"), _sc("md-ch2", "2")])
    series_id = await _make_series()

    async with session_scope() as session:
        result = await follow.check_series(session, series_id)

    assert result["enqueued"] == 2
    assert result["status"] == "ok"
    assert len(collected) == 2
    assert {t.chapter.external_id for t in collected} == {"md-ch1", "md-ch2"}

    async with session_scope() as session:
        log_count = (await session.execute(select(func.count(FollowLog.id)))).scalar_one()
        assert log_count == 1
        series = (await session.execute(
            select(Series).where(Series.id == series_id)
        )).scalar_one()
        assert series.last_checked_at is not None


@pytest.mark.asyncio
async def test_check_series_skips_existing(monkeypatch):
    collected: list = []
    monkeypatch.setattr(follow, "enqueue_download", lambda t: collected.append(t))
    _patch_chapters(monkeypatch, [_sc("md-ch1", "1"), _sc("md-ch2", "2")])
    series_id = await _make_series()

    # md-ch1 is already downloaded.
    async with session_scope() as session:
        vol = Volume(series_id=series_id, number="1", sort=1.0, language="it")
        session.add(vol)
        await session.flush()
        session.add(Chapter(
            volume_id=vol.id, number="1", sort=1.0, language="it",
            source_provider="mangadex", source_id="md-ch1",
        ))

    async with session_scope() as session:
        result = await follow.check_series(session, series_id)

    assert result["enqueued"] == 1
    assert [t.chapter.external_id for t in collected] == ["md-ch2"]


@pytest.mark.asyncio
async def test_backfill_count_limits(monkeypatch):
    collected: list = []
    monkeypatch.setattr(follow, "enqueue_download", lambda t: collected.append(t))
    _patch_chapters(monkeypatch, [
        _sc("md-ch1", "1"), _sc("md-ch2", "2"), _sc("md-ch3", "3"),
    ])
    series_id = await _make_series()

    async with session_scope() as session:
        result = await follow.backfill_series(session, series_id, count=2)

    assert result["scheduled"] == 2
    assert len(collected) == 2
    # `count` takes the latest (highest-numbered) chapters.
    assert {t.chapter.external_id for t in collected} == {"md-ch2", "md-ch3"}


@pytest.mark.asyncio
async def test_backfill_dedupes_duplicate_chapters(monkeypatch):
    """Duplicate (external_id, language) entries from the source are enqueued once."""
    collected: list = []
    monkeypatch.setattr(follow, "enqueue_download", lambda t: collected.append(t))
    _patch_chapters(monkeypatch, [_sc("dup", "1"), _sc("dup", "1"), _sc("u2", "2")])
    series_id = await _make_series()

    async with session_scope() as session:
        result = await follow.backfill_series(session, series_id)

    assert result["scheduled"] == 2
    assert {t.chapter.external_id for t in collected} == {"dup", "u2"}


@pytest.mark.asyncio
async def test_backfill_dedupes_by_number(monkeypatch):
    """One chapter per number; Italian wins when a number exists in it+en."""
    collected: list = []
    monkeypatch.setattr(follow, "enqueue_download", lambda t: collected.append(t))
    _patch_chapters(monkeypatch, [
        _sc("it-1", "1", "it"),
        _sc("en-1", "1", "en"),
        _sc("en-2a", "2", "en"),
        _sc("en-2b", "2", "en"),  # second scanlation of the same number
        _sc("it-3", "3", "it"),
    ])
    series_id = await _make_series()

    async with session_scope() as session:
        result = await follow.backfill_series(session, series_id)

    assert result["scheduled"] == 3  # numbers {1, 2, 3}, one each
    by_number = {t.chapter.number: t.chapter for t in collected}
    assert set(by_number) == {"1", "2", "3"}
    assert by_number["1"].language == "it"  # italian-first
    assert by_number["3"].language == "it"
