"""Domain health check — the cron body behind auto-fallback.

Pings every domain of every enabled source (primary + alternates) using
the source's `health_check_path` from `config/sources.yaml`, and records
the outcome via `DomainRegistry.record_success` / `record_failure`. After
3 consecutive failures a domain flips `healthy=False`, and
`DomainRegistry.pick_domain` will route scrapers to a healthy alternate.

A health check must be *cheap and quick*: we use a dedicated httpx client
with a short timeout and **no retries** (unlike the shared data client),
so an unreachable/Cloudflare-fronted domain fails fast instead of
blocking the sweep for minutes.

Called periodically by `app/scheduler/jobs.py` and on-demand by
`POST /api/settings/providers/health/check`.
"""

from __future__ import annotations

import httpx
import structlog

from app.scrapers.domain_registry import DomainRegistry
from app.settings import get_settings

logger = structlog.get_logger("mangasama.services.health")

#: Per-request timeout for a liveness probe (seconds).
HEALTH_TIMEOUT = 8.0


def make_health_client() -> httpx.AsyncClient:
    """A short-timeout, no-retry client dedicated to liveness probes."""
    return httpx.AsyncClient(
        timeout=HEALTH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": get_settings().user_agent},
    )


def _is_up(status_code: int) -> bool:
    """A domain is 'up' if it answers without a server error. 429 (rate
    limited) still means the host is alive; 4xx like 403/404 mean the host
    answered but isn't usable for scraping → treat as a failure (fallback)."""
    return status_code < 400 or status_code == 429


async def check_all_domains(*, client: httpx.AsyncClient | None = None) -> dict:
    """Ping every domain of every enabled source; update `domain_health`.

    Returns a `{checked, healthy, failed}` summary. Never raises — each
    domain is isolated so one bad host doesn't abort the sweep.
    """
    registry = DomainRegistry()
    owns_client = client is None
    if client is None:
        client = make_health_client()

    checked = healthy = failed = 0
    try:
        for source, cfg in registry.sources().items():
            if not cfg.get("enabled", True):
                continue
            scheme = cfg.get("scheme", "https")
            path = cfg.get("health_check_path") or "/"
            for domain in registry.all_domains_for(source):
                url = f"{scheme}://{domain}{path}"
                checked += 1
                try:
                    resp = await client.get(url)
                    if _is_up(resp.status_code):
                        await registry.record_success(source, domain, status_code=resp.status_code)
                        healthy += 1
                    else:
                        await registry.record_failure(source, domain, status_code=resp.status_code)
                        failed += 1
                except Exception as e:  # network error / timeout → unhealthy
                    await registry.record_failure(source, domain, status_code=None)
                    failed += 1
                    logger.info(
                        "health.domain_failed", source=source, domain=domain, error=str(e),
                    )
    finally:
        if owns_client:
            await client.aclose()

    logger.info("health.sweep_done", checked=checked, healthy=healthy, failed=failed)
    return {"checked": checked, "healthy": healthy, "failed": failed}


__all__ = ["check_all_domains", "make_health_client", "HEALTH_TIMEOUT"]
