"""Tests for the job event bus (`app/services/job_events.py`)."""

from __future__ import annotations

import asyncio

import pytest

from app.services import job_events


@pytest.fixture(autouse=True)
def _reset_bus():
    job_events.reset_for_tests()
    yield
    job_events.reset_for_tests()


@pytest.mark.asyncio
async def test_publish_reaches_subscriber():
    bus = job_events.get_job_event_bus()
    async with bus.subscribe() as q:
        job_events.publish_job({"id": 1, "status": "done"})
        ev = await asyncio.wait_for(q.get(), timeout=1)
    assert ev == {"id": 1, "status": "done"}


@pytest.mark.asyncio
async def test_fan_out_to_multiple_subscribers():
    bus = job_events.get_job_event_bus()
    async with bus.subscribe() as q1, bus.subscribe() as q2:
        assert bus.subscriber_count == 2
        job_events.publish_job({"id": 7})
        a = await asyncio.wait_for(q1.get(), timeout=1)
        b = await asyncio.wait_for(q2.get(), timeout=1)
    assert a == b == {"id": 7}
    assert bus.subscriber_count == 0  # both unsubscribed on exit


@pytest.mark.asyncio
async def test_full_subscriber_does_not_raise():
    bus = job_events.get_job_event_bus()
    async with bus.subscribe() as q:
        # Overflow the bounded queue; publish must not raise.
        for i in range(job_events._MAX_SUBSCRIBER_BACKLOG + 10):
            job_events.publish_job({"id": i})
        assert q.qsize() == job_events._MAX_SUBSCRIBER_BACKLOG


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_is_noop():
    job_events.publish_job({"id": 1})  # must not raise
