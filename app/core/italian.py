"""Italian language helpers: detection, normalisation, sort-title handling."""

from __future__ import annotations

import re
import unicodedata

# Italian articles / prepositions that should be ignored when sorting
# (`sort_title` puts "il" last so "Il nome della rosa" sorts under "N").
_ITALIAN_LOWER_SORT_PREFIXES = {
    "il", "lo", "la", "i", "gli", "le", "l",
    "un", "uno", "una",
    "the",  # for English-titled series, same convention
}


def normalize_text(s: str) -> str:
    """Lowercase + strip diacritics + collapse whitespace.

    Used for fuzzy matching: "Pokémon" and "Pokemon" should be considered
    equivalent by the search orchestrator.
    """
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unicodedata.normalize("NFC", s).lower().strip()
    return re.sub(r"\s+", " ", s)


def sort_title(title: str) -> str:
    """Return a sort-friendly version of a title: leading articles stripped.

    Example: "Il nome della rosa" -> "nome della rosa".
    """
    if not title:
        return ""
    t = title.strip()
    # Tokenise on the first whitespace.
    first, _, rest = t.partition(" ")
    if normalize_text(first) in _ITALIAN_LOWER_SORT_PREFIXES:
        return rest.strip() or t
    return t


def is_italian_language(lang: str | None) -> bool:
    """True for `it`, `ita`, `it-IT`, `Italian`."""
    if not lang:
        return False
    s = lang.lower().strip()
    return s in {"it", "ita", "it-it", "italian", "italiano", "italiana"}
