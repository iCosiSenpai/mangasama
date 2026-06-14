"""Tests for the language picker.

These are pure functions: feed in `ScrapedChapter` lists, assert the
re-ordered / filtered output. The chapter dataclass is defined in
`app.scrapers.base`.
"""

from __future__ import annotations

from app.scrapers.base import ScrapedChapter
from app.services.language_picker import (
    DEFAULT_PRIORITY,
    is_italian,
    priority_for,
    select_chapters,
)


def _ch(*, lang: str, n: str = "1", external_id: str | None = None) -> ScrapedChapter:
    return ScrapedChapter(
        source="x",
        external_id=external_id or f"id-{lang}-{n}",
        url=f"https://example.com/{lang}/{n}",
        number=n,
        language=lang,
    )


# ---------------------------------------------------------- priority_for


def test_priority_for_none_returns_default() -> None:
    assert priority_for(None) == ("it", "en")


def test_priority_for_empty_returns_default() -> None:
    assert priority_for([]) == ("it", "en")


def test_priority_for_normalises_and_lowercases() -> None:
    assert priority_for(["EN", "It", "Fr"]) == ("en", "it", "fr")


def test_priority_for_keeps_custom_order() -> None:
    assert priority_for(["fr", "en"]) == ("fr", "en")


# ---------------------------------------------------------- is_italian


def test_is_italian_recognises_variants() -> None:
    assert is_italian("it") is True
    assert is_italian("IT") is True
    assert is_italian("ita") is True
    assert is_italian("italiano") is True
    assert is_italian("it-IT") is True
    assert is_italian("en") is False
    assert is_italian(None) is False
    assert is_italian("") is False


# ---------------------------------------------------------- select_chapters


def test_select_chapters_orders_italian_first() -> None:
    out = select_chapters([
        _ch(lang="en", n="1", external_id="en-1"),
        _ch(lang="it", n="1", external_id="it-1"),
        _ch(lang="en", n="2", external_id="en-2"),
        _ch(lang="it", n="2", external_id="it-2"),
    ])
    ids = [c.external_id for c in out]
    # All `it` first (in their original order: it-1, it-2), then en.
    assert ids == ["it-1", "it-2", "en-1", "en-2"]


def test_select_chapters_preserves_order_within_language() -> None:
    out = select_chapters([
        _ch(lang="it", n="3", external_id="it-3"),
        _ch(lang="it", n="1", external_id="it-1"),
        _ch(lang="it", n="2", external_id="it-2"),
    ])
    # Within `it`, the original order is kept (stable sort).
    assert [c.external_id for c in out] == ["it-3", "it-1", "it-2"]


def test_select_chapters_with_languages_filter() -> None:
    out = select_chapters(
        [
            _ch(lang="it", n="1"),
            _ch(lang="en", n="1"),
            _ch(lang="fr", n="1"),
        ],
        languages=["it", "fr"],
    )
    # `en` is filtered out; the remaining are still it-first.
    assert [c.language for c in out] == ["it", "fr"]


def test_select_chapters_with_languages_filter_excludes_it() -> None:
    out = select_chapters(
        [
            _ch(lang="it", n="1"),
            _ch(lang="en", n="1"),
            _ch(lang="ja", n="1"),
        ],
        languages=["en"],
    )
    assert [c.language for c in out] == ["en"]


def test_select_chapters_handles_empty_input() -> None:
    assert select_chapters([]) == []


def test_select_chapters_handles_unknown_languages() -> None:
    """Unknown languages sort after the priority list, in input order."""
    out = select_chapters([
        _ch(lang="ja", external_id="ja-1"),
        _ch(lang="ko", external_id="ko-1"),
        _ch(lang="it", external_id="it-1"),
        _ch(lang="en", external_id="en-1"),
    ])
    assert [c.external_id for c in out] == ["it-1", "en-1", "ja-1", "ko-1"]


def test_select_chapters_custom_priority() -> None:
    out = select_chapters(
        [
            _ch(lang="it", external_id="it-1"),
            _ch(lang="en", external_id="en-1"),
            _ch(lang="fr", external_id="fr-1"),
        ],
        language_priority=["fr", "en", "it"],
    )
    assert [c.external_id for c in out] == ["fr-1", "en-1", "it-1"]


def test_default_priority_is_italian_first() -> None:
    assert DEFAULT_PRIORITY[0] == "it"
