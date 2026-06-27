"""Tests for Cloudflare solver dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import SourceUnavailable
from app.scrapers.cloudflare import solve_page


@pytest.mark.asyncio
async def test_solve_page_requires_solver():
    with patch("app.scrapers.cloudflare.get_settings") as gs:
        gs.return_value.cloudflare_solver = ""
        with pytest.raises(SourceUnavailable, match="CLOUDFLARE_SOLVER"):
            await solve_page("https://example.com")


@pytest.mark.asyncio
async def test_solve_flaresolverr_ok():
    payload = {
        "status": "ok",
        "solution": {
            "url": "https://www.mangaworld.mx/",
            "status": 200,
            "response": "<html>ok</html>",
            "cookies": [{"name": "cf_clearance", "value": "abc", "domain": ".mangaworld.mx"}],
        },
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("app.scrapers.cloudflare.get_settings") as gs:
        gs.return_value.cloudflare_solver = "flaresolverr"
        gs.return_value.flaresolverr_url = "http://flaresolverr:8191/v1"
        with patch("app.scrapers.cloudflare.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value = mock_client
            client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await solve_page("https://www.mangaworld.mx/")
    assert result.status_code == 200
    assert "ok" in result.html
    assert result.cookies["cf_clearance"] == "abc"
