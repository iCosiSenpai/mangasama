"""Aggregator router — combines every per-domain sub-router under one APIRouter.

`app/main.py` mounts each sub-router individually via `_try_include_routers`
so the per-module mount still works. This aggregator is provided for
future use (e.g. mounting the whole API in one shot from a different
ASGI app during testing).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    chapters,
    covers,
    follow,
    jobs,
    libraries,
    search,
    series,
    settings_api,
)

api_router = APIRouter()
api_router.include_router(libraries.router)
api_router.include_router(series.router)
api_router.include_router(chapters.router)
api_router.include_router(search.router)
api_router.include_router(follow.router)
api_router.include_router(jobs.router)
api_router.include_router(covers.router)
api_router.include_router(settings_api.router)
