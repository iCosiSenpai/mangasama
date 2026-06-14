"""Search schemas — request/response for the multi-source search endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    """Body for `POST /api/search`."""

    library_id: int = Field(..., ge=1)
    query: str = Field(..., min_length=1, max_length=200)
    # If None, defaults to `library.providers`. Each entry must be a
    # registered scraper name (`mangaworld`, `mangadex`, …).
    providers: list[str] | None = None
    # BCP-47 language codes, in priority order. Italian-first by default.
    languages: list[str] = Field(default_factory=lambda: ["it", "en"])
    # Hard cap on candidates per provider.
    limit_per_provider: int = Field(default=5, ge=1, le=20)


class SearchCandidate(BaseModel):
    """One search hit, normalized across providers."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    external_id: str
    url: str | None = None
    title: str
    alt_titles: list[str] = Field(default_factory=list)
    year: int | None = None
    cover_url: str | None = None
    # For series search this is always None; reserved for chapter search.
    language: str | None = None
    type: str | None = None
    score: float = 0.0
    # Computed: True if the provider reports an Italian translation
    # is available for this series.
    is_italian_available: bool = False


class SearchResponse(BaseModel):
    query: str
    library_id: int
    providers_used: list[str] = Field(default_factory=list)
    candidates: list[SearchCandidate] = Field(default_factory=list)
