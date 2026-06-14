"""Per-source cookie persistence.

The cookie jar is a tiny JSON file at `/config/cookies/<source>.json`.
When a Cloudflare-protected site returns `set-cookie: cf_clearance=...`,
we save it; on the next request we send it back. The TTL is 30 days
(Cloudflare's `cf_clearance` cookie itself expires in 30 minutes to
24 hours; we re-validate at 30 days for safety).

Cloudflare cookies are *per-IP* and *per-User-Agent*. If the user-agent
or egress IP changes, the cookie becomes invalid and we'll just get
another challenge. That's fine — the orchestrator falls back.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

from app.settings import get_settings

logger = structlog.get_logger("mangasama.scrapers.cookies")

DEFAULT_TTL_SECONDS = 30 * 24 * 3600  # 30 days


class CookieStore:
    """JSON-backed cookie jar for one source."""

    def __init__(self, source: str, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.source = source
        self.ttl = ttl_seconds
        settings = get_settings()
        self.path = settings.cookies_dir / f"{source}.json"

    def load(self) -> dict[str, str]:
        """Return a name->value map of fresh cookies, or {} if stale/missing."""
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("cookies.read_failed", source=self.source, error=str(e))
            return {}

        saved_at = float(data.get("_saved_at", 0))
        if time.time() - saved_at > self.ttl:
            return {}
        # Strip the metadata key.
        return {k: v for k, v in data.items() if not k.startswith("_")}

    def save(self, cookies: dict[str, str]) -> None:
        """Persist `cookies` to disk with the current timestamp."""
        payload = dict(cookies)
        payload["_saved_at"] = time.time()
        payload["_source"] = self.source
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        tmp.replace(self.path)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
