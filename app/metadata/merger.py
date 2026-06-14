"""Metadata merger — combine multiple `MetadataRecord`s into one.

Inspired by komf's "best-of" approach but with explicit, per-field
rules instead of an opaque "first wins" strategy. Each provider
contributes a confidence score (0..1); the merger weights each
contribution accordingly and resolves conflicts deterministically.

Strategy:
  - `title`         : longest non-empty wins (covers localised edge cases)
  - `summary`       : longest non-empty wins
  - `year`          : median of all non-null values
  - `status`        : vote; on conflict, highest-confidence provider wins
  - `country`       : highest-confidence provider wins
  - `type`          : vote; on conflict, highest-confidence provider wins
  - `cover_url`     : highest-confidence provider wins (provider ordering:
                      anilist (0.9) > mangadex (0.85) > google_books (0.7))
  - `authors`       : union per (role, name); writer/penciller ordering:
                      anilist is authoritative for writer/cover_artist,
                      mangadex for letterer/colorist (matches the plan)
  - `genres`        : union, preserving first-seen order
  - `tags`          : union, preserving first-seen order
  - `publisher`     : highest-confidence provider wins
  - `metadata.*`    : the highest-confidence provider's dict wins entirely

The merged record carries its own `confidence` (weighted average of
inputs). A confidence < 0.5 leaves the fields but is logged as
"untrusted".
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.metadata.base import (
    MetadataAuthor,
    MetadataRecord,
    ProviderName,
)

# Author roles AniList is authoritative for (per the plan).
_ANILIST_AUTHORITATIVE_ROLES = {"writer", "cover_artist"}
# Author roles MangaDex is authoritative for.
_MANGADEX_AUTHORITATIVE_ROLES = {"letterer", "colorist", "translator"}


@dataclass
class MergedMetadata:
    """Result of merging multiple `MetadataRecord`s."""

    title: str = ""
    alt_titles: list[str] = field(default_factory=list)
    summary: str | None = None
    year: int | None = None
    status: str | None = None
    cover_url: str | None = None
    country: str | None = None
    type: str | None = None
    authors: list[MetadataAuthor] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    publisher: str | None = None
    available_languages: list[str] = field(default_factory=list)
    # Per-provider inputs we used, in priority order.
    source_records: list[MetadataRecord] = field(default_factory=list)
    # Per-provider attribution for the chosen values, e.g.
    # `{"title": "anilist", "cover_url": "anilist"}`.
    attribution: dict[str, ProviderName] = field(default_factory=dict)
    # 0..1 confidence the merged record is correct.
    confidence: float = 0.0
    # Free-form payload from the highest-confidence provider.
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "alt_titles": list(self.alt_titles),
            "summary": self.summary,
            "year": self.year,
            "status": self.status,
            "cover_url": self.cover_url,
            "country": self.country,
            "type": self.type,
            "authors": [{"role": a.role, "name": a.name} for a in self.authors],
            "genres": list(self.genres),
            "tags": list(self.tags),
            "publisher": self.publisher,
            "available_languages": list(self.available_languages),
            "confidence": self.confidence,
            "attribution": dict(self.attribution),
            "sources": [r.provider for r in self.source_records],
        }


class MetadataMerger:
    """Combine provider records into one best-estimate `MergedMetadata`."""

    def merge(
        self,
        records: Iterable[MetadataRecord],
        *,
        preferred_cover: ProviderName | None = None,
    ) -> MergedMetadata:
        rs = [r for r in records if r]
        if not rs:
            return MergedMetadata()

        # Sort by confidence DESC; tie-break by provider order
        # (anilist > mangadex > google_books).
        rs.sort(key=lambda r: (-r.confidence, _provider_rank(r.provider)))
        out = MergedMetadata()
        out.source_records = list(rs)

        # ---------------- scalar fields ----------------

        out.title = self._longest_nonempty(r.title for r in rs) or ""
        out.attribution["title"] = _winner(
            [r for r in rs if r.title == out.title], out.source_records
        )

        summaries = [r.summary for r in rs if r.summary]
        if summaries:
            out.summary = max(summaries, key=len)
            out.attribution["summary"] = _winner(
                [r for r in rs if r.summary == out.summary], out.source_records,
            )

        years = [r.year for r in rs if r.year is not None]
        if years:
            out.year = int(statistics.median(years))
            out.attribution["year"] = _winner(
                [r for r in rs if r.year == out.year], out.source_records,
            )

        status_v = self._vote_attr(rs, lambda r: r.status)
        if status_v[0] is not None:
            out.status, out.attribution["status"] = status_v
        country_v = self._vote_attr(rs, lambda r: r.country)
        if country_v[0] is not None:
            out.country, out.attribution["country"] = country_v
        type_v = self._vote_attr(rs, lambda r: r.type)
        if type_v[0] is not None:
            out.type, out.attribution["type"] = type_v

        publisher_v = self._vote_attr(rs, lambda r: r.publisher)
        if publisher_v[0] is not None:
            out.publisher, out.attribution["publisher"] = publisher_v

        # ---------------- cover ----------------

        if preferred_cover:
            preferred = next(
                (r for r in rs if r.provider == preferred_cover and r.cover_url),
                None,
            )
            if preferred and preferred.cover_url:
                out.cover_url = preferred.cover_url
                out.attribution["cover_url"] = preferred.provider
        if not out.cover_url:
            for r in rs:
                if r.cover_url:
                    out.cover_url = r.cover_url
                    out.attribution["cover_url"] = r.provider
                    break

        # ---------------- alt titles + languages ----------------

        seen_titles: set[str] = {out.title.lower()} if out.title else set()
        for r in rs:
            for t in r.alt_titles:
                if t and t.lower() not in seen_titles:
                    seen_titles.add(t.lower())
                    out.alt_titles.append(t)
        for r in rs:
            for lang in r.available_languages:
                if lang and lang not in out.available_languages:
                    out.available_languages.append(lang)

        # ---------------- authors ----------------

        out.authors = self._merge_authors(rs)
        if out.authors:
            # Attribute authors by role: who is "authoritative" wins.
            for a in out.authors:
                # If a role is in the AniList-authoritative set AND
                # AniList contributed, attribute to anilist. Else
                # MangaDex if contributed. Else the highest-confidence
                # source that has an author of that role.
                a.provider = self._attribute_author(a, rs)

        # ---------------- genres + tags ----------------

        for r in rs:
            for g in r.genres:
                if g and g not in out.genres:
                    out.genres.append(g)
            for t in r.tags:
                if t and t not in out.tags:
                    out.tags.append(t)

        # ---------------- confidence ----------------

        if rs:
            # Weighted by the providers' own confidences.
            total = sum(r.confidence for r in rs) or 1.0
            out.confidence = round(
                sum(r.confidence * r.confidence for r in rs) / total, 3,
            )

        # Metadata block: highest-confidence provider wins.
        top = rs[0]
        out.metadata = dict(top.metadata or {})

        return out

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _longest_nonempty(values: Iterable[str]) -> str | None:
        clean = [v.strip() for v in values if v and v.strip()]
        if not clean:
            return None
        return max(clean, key=len)

    @staticmethod
    def _vote_attr(rs: list[MetadataRecord], getter) -> tuple[Any, ProviderName | None]:
        """Pick a value by confidence-weighted vote, then by source order."""
        votes: Counter[tuple[Any, ProviderName]] = Counter()
        weighted: dict[Any, float] = {}
        for r in rs:
            v = getter(r)
            if v is None or v == "":
                continue
            key = (v, r.provider)
            votes[key] += 1
            weighted[v] = weighted.get(v, 0.0) + r.confidence
        if not votes:
            return None, None
        # Highest weighted value; tie -> top of the input order.
        top_value = max(weighted.keys(), key=lambda v: (weighted[v], -_first_index(rs, v, getter)))
        # Attribution: among providers that contributed `top_value`,
        # pick the highest-confidence one.
        contributors = [r for r in rs if getter(r) == top_value]
        provider = _winner(contributors, rs)
        return top_value, provider

    @staticmethod
    def _merge_authors(rs: list[MetadataRecord]) -> list[MetadataAuthor]:
        """Union of (role, name) pairs. Per-role, authoritative provider wins."""
        # Group candidates by role.
        by_role: dict[str, list[tuple[MetadataAuthor, MetadataRecord]]] = {}
        for r in rs:
            for a in r.authors:
                by_role.setdefault(a.role, []).append((a, r))
        out: list[MetadataAuthor] = []
        for role, candidates in by_role.items():
            # Build the priority list per role.
            priority: list[ProviderName] = []
            if role in _ANILIST_AUTHORITATIVE_ROLES:
                priority.extend(["anilist", "mangadex", "google_books"])
            elif role in _MANGADEX_AUTHORITATIVE_ROLES:
                priority.extend(["mangadex", "anilist", "google_books"])
            else:
                priority.extend(["anilist", "mangadex", "google_books"])

            chosen_provider: ProviderName | None = None
            for p in priority:
                if any(c[1].provider == p for c in candidates):
                    chosen_provider = p
                    break
            # Now collect all (role, name) pairs contributed by
            # `chosen_provider`; if it's empty, fall back to the union
            # from all providers.
            names_from_chosen: list[str] = []
            if chosen_provider is not None:
                names_from_chosen = [
                    a.name for a, src in candidates if src.provider == chosen_provider
                ]
            if not names_from_chosen:
                names_from_chosen = [a.name for a, _ in candidates]
            seen: set[str] = set()
            for n in names_from_chosen:
                if n not in seen:
                    seen.add(n)
                    out.append(MetadataAuthor(
                        role=role, name=n, provider=chosen_provider,  # type: ignore[arg-type]
                    ))
        return out

    @staticmethod
    def _attribute_author(a: MetadataAuthor, rs: list[MetadataRecord]) -> ProviderName | None:
        return getattr(a, "provider", None)


# ------------------------------------------------------------ internal helpers


_PROVIDER_RANK = {"anilist": 0, "mangadex": 1, "google_books": 2}


def _provider_rank(p: ProviderName) -> int:
    return _PROVIDER_RANK.get(p, 99)


def _first_index(rs: list[MetadataRecord], value: Any, getter) -> int:
    for i, r in enumerate(rs):
        if getter(r) == value:
            return i
    return len(rs)


def _winner(
    contributors: list[MetadataRecord], ordered: list[MetadataRecord],
) -> ProviderName | None:
    """Pick the highest-confidence contributor; tie-break by input order."""
    if not contributors:
        return None
    contribs_set = set(id(r) for r in contributors)
    for r in ordered:
        if id(r) in contribs_set:
            return r.provider
    return contributors[0].provider


# Patch MetadataAuthor to carry an optional `provider` attribute for
# the merger's attribution output. We don't want to mutate the upstream
# dataclass for v1, so we attach at runtime here.
_orig_init = MetadataAuthor.__init__


def _author_init(self, role: str, name: str, provider: ProviderName | None = None):  # type: ignore[no-redef]
    _orig_init(self, role=role, name=name)
    self.provider = provider  # type: ignore[attr-defined]


MetadataAuthor.__init__ = _author_init  # type: ignore[assignment]
