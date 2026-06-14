"""ComicInfo.xml v2.1 builder.

The XML schema lives at https://anansi-project.github.io/docs/comicinfo/schemas/v2.1
We emit a subset that is well-supported by Komga, Kavita, Moon+ Reader,
and the Anansi Project's reference parser:

  Title, Series, Number, Volume, Summary
  Writer, Penciller, Inker, Colorist, Letterer, CoverArtist
  Translator, Publisher, Genre, Tags, Web, PageCount, LanguageISO
  Manga = "YesAndRightToLeft" for manga/manhwa, "Yes" for manhua/western
  StoryArc = series.title, StoryArcNumber = "{volume}.{chapter}"
  Pages block: one <Page Image=N ImageWidth=W ImageHeight=H /> per page

Notes:
  - Output is UTF-8 with NO BOM.
  - Special XML characters in text fields are escaped.
  - Empty fields are omitted (don't ship <Tag></Tag> for nothing).
  - StoryArc/StoryArcNumber is the Komga convention for grouping
    chapters under the right volume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from app.core.paths import _pad


@dataclass
class ComicPageInfo:
    """Per-page geometry for the <Pages> block."""

    index: int       # 0-based
    width: int | None = None
    height: int | None = None


@dataclass
class ComicInfo:
    """ComicInfo.xml v2.1 fields.

    Authors are grouped by role (writer/penciller/...) — multiple names
    per role are comma-joined per the schema.
    """

    title: str
    series: str
    number: str
    volume: str | int | None = None
    summary: str | None = None
    language_iso: str = "en"
    page_count: int = 0
    web: str | None = None
    publisher: str | None = None
    manga: bool = True              # True => manga/manhwa; False => western
    right_to_left: bool = True      # used only if manga=True
    authors: dict[str, list[str]] = field(default_factory=dict)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    translator: str | None = None
    story_arc: str | None = None
    story_arc_number: str | None = None
    pages: list[ComicPageInfo] = field(default_factory=list)

    # --- role helpers ---------------------------------------------------

    def add_author(self, role: str, name: str) -> None:
        """Add a name under a role. Recognised roles: writer, penciller,
        inker, colorist, letterer, cover_artist, editor, translator.
        Unknown roles are still emitted (the schema is permissive).
        """
        if not name:
            return
        bucket = self.authors.setdefault(role, [])
        if name not in bucket:
            bucket.append(name)


# ----- XML helpers ----------------------------------------------------------


_KNOWN_LIST_FIELDS = {
    "Writer", "Penciller", "Inker", "Colorist", "Letterer",
    "CoverArtist", "Editor", "Translator", "Genre", "Tags", "Web",
}


def _set_if_present(parent: ET.Element, tag: str, value: str | None) -> None:
    if value is None or value == "":
        return
    el = ET.SubElement(parent, tag)
    el.text = value


def _set_list(parent: ET.Element, tag: str, items: Iterable[str]) -> None:
    items = [i for i in items if i]
    if not items:
        return
    el = ET.SubElement(parent, tag)
    el.text = ", ".join(items)


def _manga_value(manga: bool, right_to_left: bool) -> str:
    if not manga:
        return "No"
    return "YesAndRightToLeft" if right_to_left else "Yes"


# ----- public API ------------------------------------------------------------


def build_xml(info: ComicInfo) -> bytes:
    """Render the ComicInfo.xml v2.1 document as UTF-8 bytes (no BOM)."""
    root = ET.Element("ComicInfo")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema-instance")

    _set_if_present(root, "Title", info.title)
    _set_if_present(root, "Series", info.series)
    _set_if_present(root, "Number", info.number)
    if info.volume not in (None, "", "0"):
        _set_if_present(root, "Volume", str(info.volume))
    _set_if_present(root, "Summary", info.summary)
    _set_if_present(root, "LanguageISO", info.language_iso)
    _set_if_present(root, "PageCount", str(info.page_count) if info.page_count else None)
    _set_if_present(root, "Web", info.web)
    _set_if_present(root, "Publisher", info.publisher)
    _set_if_present(root, "Manga", _manga_value(info.manga, info.right_to_left))

    # Authors by role — emit each non-empty role.
    for role in (
        "Writer", "Penciller", "Inker", "Colorist", "Letterer",
        "CoverArtist", "Editor",
    ):
        names = info.authors.get(role.lower()) or info.authors.get(role) or []
        _set_list(root, role, names)

    _set_list(root, "Genre", info.genres)
    _set_list(root, "Tags", info.tags)
    _set_if_present(root, "Translator", info.translator)
    _set_if_present(root, "StoryArc", info.story_arc)
    _set_if_present(root, "StoryArcNumber", info.story_arc_number)

    # Pages block
    if info.pages:
        pages = ET.SubElement(root, "Pages")
        for p in info.pages:
            pe = ET.SubElement(pages, "Page")
            pe.set("Image", str(p.index))
            if p.width is not None:
                pe.set("ImageWidth", str(p.width))
            if p.height is not None:
                pe.set("ImageHeight", str(p.height))

    # Serialize. UTF-8, no BOM, no XML declaration (Komga tolerates either,
    # and dropping the decl gives a slightly smaller + more portable file).
    body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    return body


def story_arc_number(volume: str | int | None, chapter: str) -> str:
    """Format the Komga-style story-arc number: '{volume}.{chapter}'.

    The chapter portion is zero-padded to 3 digits so sorting is stable
    in readers that group by StoryArcNumber.
    """
    v = "" if volume in (None, "", "0") else str(volume)
    return f"{v}.{_pad(chapter)}" if v else _pad(chapter)
