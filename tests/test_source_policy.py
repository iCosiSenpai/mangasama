"""Tests for source enablement policy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from app.scrapers.domain_registry import DomainRegistry
from app.scrapers.source_policy import enabled_scraper_names, is_scraper_available, is_source_enabled


def _write_sources(tmp_path: Path, sources: dict) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump({"sources": sources}), encoding="utf-8")
    return path


def test_is_source_enabled_respects_yaml(tmp_path):
    path = _write_sources(tmp_path, {
        "mangadex": {"enabled": True},
        "bato": {"enabled": False},
    })
    reg = DomainRegistry(sources_path=path)
    assert is_source_enabled("mangadex", registry=reg)
    assert not is_source_enabled("bato", registry=reg)


def test_is_scraper_available_requires_registry_and_yaml(tmp_path):
    path = _write_sources(tmp_path, {
        "mangadex": {"enabled": True},
        "bato": {"enabled": True},
    })
    reg = DomainRegistry(sources_path=path)
    assert is_scraper_available("mangadex", registry=reg)
    assert not is_scraper_available("bato", registry=reg)


def test_env_toggle_disables_mangapark(tmp_path):
    path = _write_sources(tmp_path, {"mangapark": {"enabled": True}})
    reg = DomainRegistry(sources_path=path)
    with patch("app.scrapers.source_policy.get_settings") as gs:
        gs.return_value.scraper_mangapark_enabled = False
        assert not is_source_enabled("mangapark", registry=reg)


def test_enabled_scraper_names_lists_implemented_only(tmp_path):
    path = _write_sources(tmp_path, {
        "mangadex": {"enabled": True},
        "mangaworld": {"enabled": True},
        "bato": {"enabled": True},
    })
    reg = DomainRegistry(sources_path=path)
    names = enabled_scraper_names(registry=reg)
    assert "mangadex" in names
    assert "mangaworld" in names
    assert "bato" not in names
