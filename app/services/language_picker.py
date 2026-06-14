"""Italian-first language selection across scrapers.

Different scrapers return chapters in different languages:
  - MangaDex: feed supports a `translatedLanguage[]` filter; you ask
    for `["it", "en"]` and get both mixed.
  - MangaWorld: only ships Italian scanlations.
  - MangaEden: only ships Italian or English depending on path.
  - Bato / MangaPark: multi-language, you pick.

This module gives a single entry point that, given a list of
`ScrapedChapter`, returns the same list filtered / reordered by
priority.

The default priority is `[it, en, ...]` (anything else last). The
library / series can override the priority via the `language_priority`
JSON column on `libraries` / `series` (set in step 8+).
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.italian import is_italian_language
from app.scrapers.base import ScrapedChapter

DEFAULT_PRIORITY: tuple[str, ...] = ("it", "en")


def priority_for(language_priority: Iterable[str] | None) -> tuple[str, ...]:
    """Return the effective priority tuple.

    `None` or empty list -> `[it, en]`.
    Always keeps the default italian-first at the front unless the
    caller explicitly asked for something else first.
    """
    if not language_priority:
        return DEFAULT_PRIORITY
    p = [lang.strip().lower() for lang in language_priority if lang and lang.strip()]
    return tuple(p) if p else DEFAULT_PRIORITY


def _language_rank(lang: str, priority: tuple[str, ...]) -> tuple[int, str]:
    """Sort key: lower is better. Unknown langs sort after the priority list."""
    lang = (lang or "").lower()
    if lang in priority:
        return (priority.index(lang), lang)
    return (len(priority), lang)


def select_chapters(
    chapters: Iterable[ScrapedChapter],
    *,
    language_priority: Iterable[str] | None = None,
    languages: Iterable[str] | None = None,
) -> list[ScrapedChapter]:
    """Filter + sort `chapters` by language priority.

    Args:
        chapters: the raw list from a scraper.
        language_priority: ordered list of BCP-47 codes; default `[it, en]`.
        languages: if set, only chapters whose language is in this set
            are kept (still re-ordered by priority).

    Returns:
        A new list. Original ordering *within* a language is preserved.
    """
    prio = priority_for(language_priority)
    allowed = {l.lower() for l in languages} if languages else None

    out: list[ScrapedChapter] = []
    for ch in chapters:
        lang = (ch.language or "").lower()
        if allowed is not None and lang not in allowed:
            continue
        out.append(ch)

    # Stable sort: by language rank; chapters with the same language keep
    # the order they came in (e.g. chronological from the scraper).
    out.sort(key=lambda c: _language_rank(c.language, prio))
    return out


def is_italian(language: str | None) -> bool:
    """Convenience: is `language` an Italian variant?"""
    return is_italian_language(language or "")
