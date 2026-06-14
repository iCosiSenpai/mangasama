"""Tests for the ComicInfo v2.1 builder.

We assert structure (which elements exist), not exact byte equality of
the XML — Python's xml.etree normalizes whitespace in element.text in
version-dependent ways. For end-to-end "did the CBZ end up correct",
see tests/test_cbz.py.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from app.services.comicinfo import (
    ComicInfo,
    ComicPageInfo,
    build_xml,
    story_arc_number,
)


def _root(info: ComicInfo) -> ET.Element:
    body = build_xml(info)
    return ET.fromstring(body)


# ---------------------------------------------------------- basic structure


def test_root_element_is_comicinfo() -> None:
    root = _root(ComicInfo(title="x", series="x", number="1"))
    assert root.tag == "ComicInfo"


def test_minimal_required_fields_present() -> None:
    info = ComicInfo(title="Ch 1", series="Naruto", number="1", page_count=10)
    root = _root(info)
    assert root.findtext("Title") == "Ch 1"
    assert root.findtext("Series") == "Naruto"
    assert root.findtext("Number") == "1"


# --------------------------------------------------------- author by role


def test_authors_are_comma_joined_per_role() -> None:
    info = ComicInfo(title="t", series="s", number="1")
    info.add_author("writer", "Alice")
    info.add_author("writer", "Bob")
    info.add_author("penciller", "Carol")
    root = _root(info)
    # Order-preserved: Alice then Bob, then Carol in penciller.
    writers = root.findtext("Writer")
    pencillers = root.findtext("Penciller")
    assert writers == "Alice, Bob"
    assert pencillers == "Carol"


def test_empty_role_omitted() -> None:
    info = ComicInfo(title="t", series="s", number="1")
    info.add_author("writer", "")
    info.add_author("writer", "Real Name")
    root = _root(info)
    assert root.findtext("Writer") == "Real Name"


def test_blank_role_bucket_omitted_from_xml() -> None:
    info = ComicInfo(title="t", series="s", number="1")
    # No authors added.
    root = _root(info)
    assert root.find("Writer") is None
    assert root.find("Penciller") is None


# ---------------------------------------------------------- manga direction


def test_manga_value_for_japanese_manga() -> None:
    info = ComicInfo(
        title="t", series="s", number="1",
        manga=True, right_to_left=True,
    )
    assert _root(info).findtext("Manga") == "YesAndRightToLeft"


def test_manga_value_for_left_to_right_manga() -> None:
    info = ComicInfo(
        title="t", series="s", number="1",
        manga=True, right_to_left=False,
    )
    assert _root(info).findtext("Manga") == "Yes"


def test_manga_value_for_western_comic() -> None:
    info = ComicInfo(
        title="t", series="s", number="1",
        manga=False,
    )
    assert _root(info).findtext("Manga") == "No"


# --------------------------------------------------------------------- pages


def test_pages_block_with_geometry() -> None:
    info = ComicInfo(
        title="t", series="s", number="1",
        pages=[
            ComicPageInfo(index=0, width=800, height=1200),
            ComicPageInfo(index=1, width=800, height=1200),
        ],
    )
    root = _root(info)
    pages = root.find("Pages")
    assert pages is not None
    children = pages.findall("Page")
    assert [c.get("Image") for c in children] == ["0", "1"]
    assert all(c.get("ImageWidth") == "800" for c in children)
    assert all(c.get("ImageHeight") == "1200" for c in children)


def test_pages_block_absent_when_no_pages() -> None:
    info = ComicInfo(title="t", series="s", number="1")
    assert _root(info).find("Pages") is None


# ----------------------------------------------------------------- list fields


def test_genres_and_tags_comma_joined() -> None:
    info = ComicInfo(
        title="t", series="s", number="1",
        genres=["Action", "Mystery"],
        tags=["On hiatus", "Scanlated by Foo"],
    )
    root = _root(info)
    assert root.findtext("Genre") == "Action, Mystery"
    assert root.findtext("Tags") == "On hiatus, Scanlated by Foo"


# ------------------------------------------------------------ escape safety


def test_special_chars_in_text_are_escaped() -> None:
    info = ComicInfo(
        title="A & B <c>", series="Q?", number="1",
        summary="Has 'quotes' & <tags>",
    )
    # Must not raise and must decode back to the originals.
    body = build_xml(info)
    text = body.decode("utf-8")
    assert "A &amp; B &lt;c&gt;" in text
    assert "Q?" in text  # '?' is not XML-special
    assert "&apos;quotes&apos;" in text or "'quotes'" in text
    # The escaped form must round-trip on parse.
    root = ET.fromstring(text)
    assert root.findtext("Title") == "A & B <c>"


# ---------------------------------------------------- story-arc number helper


def test_story_arc_number_pads_chapter() -> None:
    assert story_arc_number("1", "1") == "1.001"
    assert story_arc_number("1", "10") == "1.010"
    assert story_arc_number(None, "5") == "005"


def test_story_arc_number_decimal_chapter() -> None:
    assert story_arc_number("2", "1.5") == "2.001.5"
    # When no volume, just the padded chapter.
    assert story_arc_number(None, "1.5") == "001.5"
