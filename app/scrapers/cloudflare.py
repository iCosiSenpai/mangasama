"""Cloudflare challenge solver dispatch.

Supports FlareSolverr (recommended in Docker via the optional sidecar).
Playwright is reserved for a future implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.core.exceptions import SourceUnavailable
from app.settings import get_settings

logger = structlog.get_logger("mangasama.scrapers.cloudflare")


@dataclass(frozen=True)
class SolvedPage:
    """Result of a successful Cloudflare solve."""

    url: str
    status_code: int
    html: str
    cookies: dict[str, str]


async def solve_page(url: str, *, max_timeout_ms: int = 60_000) -> SolvedPage:
    """Solve a Cloudflare challenge for `url` using the configured solver.

    Raises:
        SourceUnavailable: when no solver is configured or solving fails.
    """
    settings = get_settings()
    if settings.cloudflare_solver == "flaresolverr":
        return await _solve_flaresolverr(url, max_timeout_ms=max_timeout_ms)
    if settings.cloudflare_solver == "playwright":
        raise SourceUnavailable(
            "Playwright Cloudflare solver is not implemented yet",
            source="cloudflare",
        )
    raise SourceUnavailable(
        "Cloudflare challenge and CLOUDFLARE_SOLVER is not set",
        source="cloudflare",
    )


async def _solve_flaresolverr(url: str, *, max_timeout_ms: int) -> SolvedPage:
    """Call the FlareSolverr HTTP API and return cookies + HTML."""
    settings = get_settings()
    endpoint = settings.flaresolverr_url.rstrip("/")
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": max_timeout_ms,
    }
    try:
        async with httpx.AsyncClient(timeout=max_timeout_ms / 1000 + 10) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("cloudflare.flaresolverr_failed", url=url, error=str(e))
        raise SourceUnavailable(
            f"FlareSolverr request failed: {e}",
            source="cloudflare",
        ) from e

    if data.get("status") != "ok":
        msg = data.get("message") or "FlareSolverr returned non-ok status"
        raise SourceUnavailable(msg, source="cloudflare")

    solution: dict[str, Any] = data.get("solution") or {}
    status_code = int(solution.get("status") or 0)
    html = str(solution.get("response") or "")
    cookies: dict[str, str] = {}
    for item in solution.get("cookies") or []:
        if isinstance(item, dict) and item.get("name"):
            cookies[str(item["name"])] = str(item.get("value") or "")

    if status_code >= 400 or not html:
        raise SourceUnavailable(
            f"FlareSolverr solved but page returned HTTP {status_code}",
            source="cloudflare",
            status_code=status_code or None,
        )

    logger.info(
        "cloudflare.flaresolverr_ok",
        url=url,
        status=status_code,
        cookie_count=len(cookies),
    )
    return SolvedPage(
        url=str(solution.get("url") or url),
        status_code=status_code,
        html=html,
        cookies=cookies,
    )


__all__ = ["SolvedPage", "solve_page"]
