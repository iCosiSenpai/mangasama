"""Tests for the 4 folder strategies.

These are pure functions (no I/O) so we use tmp_path to assert the
generated layout. `create_dirs=True` makes the resolver mkdir-p, which
is also tested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.folder_strategy import (
    LIBRARY_FOLDER_STRATEGIES,
    SeriesVolumeChapter,
    list_strategies,
    resolve_path,
)


def _ctx(**overrides) -> SeriesVolumeChapter:
    base = dict(
        series_title="Naruto",
        chapter_number="1",
        chapter_title="Uzumaki Naruto",
        language="it",
        volume_number="1",
    )
    base.update(overrides)
    return SeriesVolumeChapter(**base)


# ------------------------------------------------------------ strategy count


def test_list_strategies_returns_the_four_known_ones() -> None:
    names = set(list_strategies())
    assert names == {
        "series_volume_chapter",
        "series_volume",
        "chapter_flat",
        "onefile_per_volume",
    }
    assert names == set(LIBRARY_FOLDER_STRATEGIES)


def test_resolve_path_rejects_unknown_strategy(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown folder strategy"):
        resolve_path("nonexistent", tmp_path, _ctx())


# --------------------------------------------------------- series_volume_chapter


def test_strategy_series_volume_chapter_layout(tmp_path: Path) -> None:
    cp = resolve_path(
        "series_volume_chapter", tmp_path, _ctx(), create_dirs=False,
    )
    assert cp.folder_parts == ("Naruto", "Volume 001")
    assert cp.path == tmp_path / "Naruto" / "Volume 001" / "Naruto - ch001 - Uzumaki Naruto (it).cbz"
    assert cp.parent == tmp_path / "Naruto" / "Volume 001"


def test_strategy_series_volume_chapter_creates_dirs(tmp_path: Path) -> None:
    cp = resolve_path("series_volume_chapter", tmp_path, _ctx())
    assert cp.parent.exists()
    assert cp.parent.is_dir()


# ----------------------------------------------------------------- series_volume


def test_strategy_series_volume_omits_chapter_title_in_filename(tmp_path: Path) -> None:
    cp = resolve_path("series_volume", tmp_path, _ctx(), create_dirs=False)
    assert cp.path == tmp_path / "Naruto" / "Volume 001" / "Naruto - ch001 (it).cbz"
    # Title is intentionally not in the filename for this strategy.
    assert "Uzumaki" not in cp.path.name


# ---------------------------------------------------------------- chapter_flat


def test_strategy_chapter_flat_has_no_volume_folder(tmp_path: Path) -> None:
    cp = resolve_path("chapter_flat", tmp_path, _ctx(), create_dirs=False)
    assert cp.folder_parts == ("Naruto",)
    assert cp.path == tmp_path / "Naruto" / "Naruto - ch001 - Uzumaki Naruto (it).cbz"
    assert "Volume" not in cp.path.parts[-2]


# ----------------------------------------------------------- onefile_per_volume


def test_strategy_onefile_per_volume_includes_vol_and_ch(tmp_path: Path) -> None:
    cp = resolve_path("onefile_per_volume", tmp_path, _ctx(), create_dirs=False)
    assert cp.path == tmp_path / "Naruto" / "Volume 001" / "Naruto - Vol001 Ch001.cbz"
    # Language is intentionally not in the filename here.
    assert "(it)" not in cp.path.name


# -------------------------------------------------------------------- number pad


def test_decimal_chapter_is_padded(tmp_path: Path) -> None:
    cp = resolve_path(
        "chapter_flat", tmp_path,
        _ctx(chapter_number="1.5"), create_dirs=False,
    )
    assert "ch001.5" in cp.path.name


def test_three_digit_chapter_is_kept_intact(tmp_path: Path) -> None:
    cp = resolve_path(
        "chapter_flat", tmp_path,
        _ctx(chapter_number="120"), create_dirs=False,
    )
    assert "ch120" in cp.path.name


def test_missing_volume_defaults_to_volume_001(tmp_path: Path) -> None:
    cp = resolve_path(
        "series_volume_chapter", tmp_path,
        _ctx(volume_number=None), create_dirs=False,
    )
    assert "Volume 001" in cp.path.parts


def test_missing_language_omits_parens(tmp_path: Path) -> None:
    cp = resolve_path(
        "chapter_flat", tmp_path,
        _ctx(language=None), create_dirs=False,
    )
    assert "(it)" not in cp.path.name
    assert "Uzumaki" in cp.path.name


# ----------------------------------------------------- filesystem-safe sanitization


def test_unsafe_title_is_sanitized(tmp_path: Path) -> None:
    cp = resolve_path(
        "chapter_flat", tmp_path,
        _ctx(series_title='A/B:C*?"<>|'), create_dirs=False,
    )
    # No forbidden character may survive in the final folder name.
    folder = cp.path.parts[-2]
    for ch in r'\/:*?"<>|':
        assert ch not in folder, f"unsafe char {ch!r} leaked into {folder!r}"
    # And the result must be non-empty (we never return the empty string).
    assert folder
    # Trailing underscores may be stripped by `safe_filename` (Windows
    # friendliness); we only assert the leading portion is preserved.
    assert folder.startswith("A_B_C")
