"""Metadata package init."""

from app.metadata.anilist import AniListProvider
from app.metadata.base import (
    BaseMetadataProvider,
    Confidence,
    MetadataAuthor,
    MetadataCandidate,
    MetadataRecord,
    ProviderName,
)
from app.metadata.cover_cache import fetch_and_cache
from app.metadata.mangadex import MangaDexMetadataProvider
from app.metadata.merger import MergedMetadata, MetadataMerger

__all__ = [
    "AniListProvider",
    "BaseMetadataProvider",
    "Confidence",
    "MangaDexMetadataProvider",
    "MergedMetadata",
    "MetadataAuthor",
    "MetadataCandidate",
    "MetadataMerger",
    "MetadataRecord",
    "ProviderName",
    "fetch_and_cache",
]
