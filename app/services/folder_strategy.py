"""Folder strategies: where to write a chapter's CBZ on disk.

A library declares ONE strategy. The downloader asks this module for
"given a series + volume + chapter, what is the absolute file path?",
and we compute it. The file name itself uses `app.core.paths`.

Four strategies ship in v1:

  1. `series_volume_chapter` (default, Komga-style)
       <root>/<Series>/Volume 00X/Series Title - ch001 - title (it).cbz
  2. `series_volume`
       <root>/<Series>/Volume 00X/Series Title - ch001.cbz
       (volume folder present but the per-chapter file is flat inside)
  3. `chapter_flat`
       <root>/<Series>/Series Title - ch001.cbz
  4. `onefile_per_volume`
       <root>/<Series>/Volume 00X/Series Title - Vol00X Ch001.cbz
       (still per-chapter CBZ, but filename carries the volume number
       explicitly; the volume folder is still created for compatibility)

Adding a strategy = register a new function in `_STRATEGIES` and
declare it in the `Library` model / `LIBRARY_FOLDER_STRATEGIES` constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from app.core.paths import chapter_filename, ensure_dir, safe_filename, volume_folder_name

FolderStrategy = Literal[
    "series_volume_chapter",
    "series_volume",
    "chapter_flat",
    "onefile_per_volume",
]

LIBRARY_FOLDER_STRATEGIES: tuple[FolderStrategy, ...] = (
    "series_volume_chapter",
    "series_volume",
    "chapter_flat",
    "onefile_per_volume",
)


@dataclass(frozen=True)
class SeriesVolumeChapter:
    """A small value object for the (series, volume, chapter) tuple."""

    series_title: str
    chapter_number: str
    chapter_title: str | None = None
    language: str | None = None
    volume_number: str | None = None


@dataclass(frozen=True)
class ChapterPath:
    """The absolute file path + the parent directory we expect to exist."""

    path: Path
    parent: Path
    folder_parts: tuple[str, ...]   # e.g. ("Naruto", "Volume 001") — for display


# ---------------------------------------------------------------- strategies


def _series_folder(series_title: str) -> str:
    return safe_filename(series_title)


def strategy_series_volume_chapter(
    root: Path, ctx: SeriesVolumeChapter,
) -> ChapterPath:
    """<root>/<Series>/Volume 00X/Series - ch001 - title (it).cbz (Komga default)."""
    series = _series_folder(ctx.series_title)
    volume = volume_folder_name(ctx.volume_number or "1")
    parent = root / series / volume
    fname = chapter_filename(
        ctx.series_title, ctx.chapter_number, ctx.chapter_title, language=ctx.language,
    )
    return ChapterPath(path=parent / fname, parent=parent, folder_parts=(series, volume))


def strategy_series_volume(
    root: Path, ctx: SeriesVolumeChapter,
) -> ChapterPath:
    """<root>/<Series>/Volume 00X/Series - ch001.cbz (chapter title omitted in name)."""
    series = _series_folder(ctx.series_title)
    volume = volume_folder_name(ctx.volume_number or "1")
    parent = root / series / volume
    fname = chapter_filename(
        ctx.series_title, ctx.chapter_number, None, language=ctx.language,
    )
    return ChapterPath(path=parent / fname, parent=parent, folder_parts=(series, volume))


def strategy_chapter_flat(
    root: Path, ctx: SeriesVolumeChapter,
) -> ChapterPath:
    """<root>/<Series>/Series - ch001 - title (it).cbz (no volume folder)."""
    series = _series_folder(ctx.series_title)
    parent = root / series
    fname = chapter_filename(
        ctx.series_title, ctx.chapter_number, ctx.chapter_title, language=ctx.language,
    )
    return ChapterPath(path=parent / fname, parent=parent, folder_parts=(series,))


def strategy_onefile_per_volume(
    root: Path, ctx: SeriesVolumeChapter,
) -> ChapterPath:
    """<root>/<Series>/Volume 00X/Series - Vol00X Ch001.cbz.

    Per the v1 design note: still one CBZ per chapter (preserves reading
    progress), but the filename embeds the volume number explicitly. The
    volume folder is created for tooling compatibility.
    """
    series = _series_folder(ctx.series_title)
    volume_label = volume_folder_name(ctx.volume_number or "1")
    parent = root / series / volume_label
    fname = (
        f"{safe_filename(ctx.series_title)} - "
        f"Vol{_pad_vol(ctx.volume_number or '1')} "
        f"Ch{_pad_ch(ctx.chapter_number)}.cbz"
    )
    return ChapterPath(
        path=parent / fname, parent=parent, folder_parts=(series, volume_label),
    )


_STRATEGIES: dict[FolderStrategy, Callable[[Path, SeriesVolumeChapter], ChapterPath]] = {
    "series_volume_chapter": strategy_series_volume_chapter,
    "series_volume": strategy_series_volume,
    "chapter_flat": strategy_chapter_flat,
    "onefile_per_volume": strategy_onefile_per_volume,
}


# --------------------------------------------------------------- public api


def resolve_path(
    strategy: FolderStrategy,
    root: Path,
    ctx: SeriesVolumeChapter,
    *,
    create_dirs: bool = True,
) -> ChapterPath:
    """Resolve `ctx` to a `ChapterPath` and optionally create the parent dir."""
    if strategy not in _STRATEGIES:
        raise ValueError(
            f"Unknown folder strategy {strategy!r}. "
            f"Supported: {sorted(_STRATEGIES)}"
        )
    cp = _STRATEGIES[strategy](Path(root), ctx)
    if create_dirs:
        ensure_dir(cp.parent)
    return cp


def list_strategies() -> list[FolderStrategy]:
    return list(_STRATEGIES.keys())


# ------------------------------------------------------------- internal pads


def _pad_vol(num: str) -> str:
    """`1` -> `001`, `10` -> `010`, `1.5` -> `001.5`."""
    s = str(num).strip() or "1"
    if "." in s:
        a, _, b = s.partition(".")
        try:
            return f"{int(a):03d}.{b}"
        except ValueError:
            return s
    try:
        return f"{int(s):03d}"
    except ValueError:
        return s


def _pad_ch(num: str) -> str:
    """Like `_pad_vol` but defaults to `'001'` for empty/invalid."""
    s = str(num).strip() or "1"
    if "." in s:
        a, _, b = s.partition(".")
        try:
            return f"{int(a):03d}.{b}"
        except ValueError:
            return s
    try:
        return f"{int(s):03d}"
    except ValueError:
        return s
