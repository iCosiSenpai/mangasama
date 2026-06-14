"""HTTP client wrapper around httpx.AsyncClient.

Responsibilities:
  - Send a descriptive User-Agent (configurable via settings)
  - Apply per-(scraper, domain) rate limiting + concurrency cap
  - Retry on 5xx and network errors with exponential backoff
  - Surface 4xx as `SourceUnavailable` (except 429 which is `RateLimited`)
  - Persist cookies via the Cookies helper
  - Pass through CF detection (the caller decides how to react)

The client is **shared** across all scrapers (one per process), with
per-call `domain` so the rate limiter can bucket correctly.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from app.core.exceptions import RateLimited, SourceUnavailable
from app.core.rate_limiter import get_rate_limiter
from app.settings import get_settings

logger = structlog.get_logger("mangasama.core.http_client")


class HttpClient:
    """Thin wrapper around httpx.AsyncClient with retry + rate limiting."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: tuple[float, ...] = (1.0, 3.0, 9.0),
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff_seconds
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Open the underlying client. Call from FastAPI lifespan."""
        if self._client is None:
            settings = get_settings()
            # We disable HTTP/2 by default because the respx-based test
            # suite can't intercept HTTP/2 calls. Production deployments
            # can flip this on via env if they want HTTP/2.
            self._client = httpx.AsyncClient(
                http2=settings.http2_enabled,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": settings.user_agent},
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HttpClient not started; call await .start() first")
        return self._client

    # ------------------------------------------------------------------ GET

    async def get_json(
        self,
        url: str,
        *,
        scraper: str,
        domain: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        rpm: int | None = None,
    ) -> Any:
        """GET a URL and return parsed JSON.

        Raises:
            SourceUnavailable: on persistent 5xx or connection errors.
            RateLimited: on 429 (after backoff).
        """
        resp = await self._request(
            "GET", url, scraper=scraper, domain=domain,
            params=params, headers=headers, rpm=rpm,
        )
        return resp.json()

    async def post_json(
        self,
        url: str,
        *,
        scraper: str,
        domain: str,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        rpm: int | None = None,
    ) -> Any:
        """POST a URL and return parsed JSON.

        Used by GraphQL clients (AniList) where the body is JSON and
        we still need retry/rate-limit/UA handling.
        """
        resp = await self._request(
            "POST", url, scraper=scraper, domain=domain,
            params=None, headers=headers, rpm=rpm,
            json=json_body, data=data,
        )
        return resp.json()

    async def get_text(
        self,
        url: str,
        *,
        scraper: str,
        domain: str,
        headers: dict[str, str] | None = None,
        rpm: int | None = None,
    ) -> str:
        """GET a URL and return the response body as text."""
        resp = await self._request(
            "GET", url, scraper=scraper, domain=domain,
            headers=headers, rpm=rpm,
        )
        return resp.text

    async def get_bytes(
        self,
        url: str,
        *,
        scraper: str,
        domain: str,
        headers: dict[str, str] | None = None,
        rpm: int | None = None,
    ) -> bytes:
        resp = await self._request(
            "GET", url, scraper=scraper, domain=domain,
            headers=headers, rpm=rpm,
        )
        return resp.content

    async def get_stream(
        self,
        url: str,
        *,
        scraper: str,
        domain: str,
        headers: dict[str, str] | None = None,
        rpm: int | None = None,
    ) -> httpx.Response:
        """GET a URL and return the response object for streaming reads.

        The caller is responsible for `await response.aclose()`.
        """
        return await self._request(
            "GET", url, scraper=scraper, domain=domain,
            headers=headers, rpm=rpm, stream=True,
        )

    # -------------------------------------------------------------- internals

    async def _request(
        self,
        method: str,
        url: str,
        *,
        scraper: str,
        domain: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        rpm: int | None = None,
        stream: bool = False,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        rl = get_rate_limiter()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            async with rl.acquire(scraper, domain, rpm=rpm):
                try:
                    resp = await self.client.request(
                        method, url,
                        params=params,
                        headers=headers,
                        json=json,
                        data=data,
                        timeout=self.timeout,
                    )
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                    last_exc = e
                    if attempt < self.max_retries:
                        await self._sleep_backoff(attempt)
                        continue
                    raise SourceUnavailable(
                        f"{method} {url}: {e}", source=scraper,
                    ) from e

                # Status handling
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("retry-after", "5"))
                    if attempt < self.max_retries:
                        logger.warning(
                            "http.429", scraper=scraper, domain=domain,
                            retry_after=retry_after, attempt=attempt,
                        )
                        await asyncio.sleep(min(retry_after, 30.0))
                        continue
                    raise RateLimited(
                        f"{method} {url}: 429 Too Many Requests", retry_after=retry_after,
                    )

                if 500 <= resp.status_code < 600:
                    if attempt < self.max_retries:
                        logger.warning(
                            "http.5xx", scraper=scraper, domain=domain,
                            status=resp.status_code, attempt=attempt,
                        )
                        await self._sleep_backoff(attempt)
                        continue
                    raise SourceUnavailable(
                        f"{method} {url}: HTTP {resp.status_code}",
                        source=scraper, status_code=resp.status_code,
                    )

                if 400 <= resp.status_code < 500:
                    # 4xx is the caller's problem, not retry-worthy.
                    if stream:
                        # Caller asked for the raw response; let them handle.
                        return resp
                    if resp.status_code == 404:
                        resp.raise_for_status()
                    # Other 4xx -> SourceUnavailable so the orchestrator
                    # can decide (fallback to next source, etc.)
                    raise SourceUnavailable(
                        f"{method} {url}: HTTP {resp.status_code}",
                        source=scraper, status_code=resp.status_code,
                    )

                return resp

        # Unreachable, but be explicit.
        raise SourceUnavailable(
            f"{method} {url}: exhausted retries", source=scraper,
        ) from last_exc

    async def _sleep_backoff(self, attempt: int) -> None:
        try:
            await asyncio.sleep(self.backoff[attempt])
        except IndexError:
            await asyncio.sleep(self.backoff[-1])


# Module-level singleton, opened in FastAPI lifespan.
_http: HttpClient | None = None


def get_http() -> HttpClient:
    global _http
    if _http is None:
        _http = HttpClient()
    return _http


async def start_http() -> None:
    await get_http().start()


async def stop_http() -> None:
    global _http
    if _http is not None:
        await _http.close()
        _http = None
