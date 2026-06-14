"""Tests for the CBZ packager.

The headline assertion is a "golden hash" test: packaging the same
input twice yields the same SHA-256 because we pin the ZIP entry
timestamps to 1980-01-01. This is what guarantees that the SHA we
store in `chapters.sha256` is stable across re-packs.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.cbz import CbzPackager, PageBlob
from app.services.comicinfo import ComicInfo

# ----------------------------------------------------------- helpers


def _solid_page(color: tuple[int, int, int], size: tuple[int, int] = (50, 50)) -> bytes:
    """A deterministic JPEG page of a single solid color."""
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@pytest.fixture
def packager() -> CbzPackager:
    return CbzPackager()


@pytest.fixture
def sample_info() -> ComicInfo:
    return ComicInfo(
        title="Test Chapter 1",
        series="Test Series",
        number="1",
        volume="1",
        language_iso="en",
        web="https://example.com/series/1",
        manga=True,
        right_to_left=True,
        story_arc="Test Series",
        story_arc_number="1.001",
    )
    # `page_count` is patched at build time by the packager.


# --------------------------------------------------------------- basic build


def test_build_creates_file_with_cbz_contents(packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo) -> None:
    pages = [
        PageBlob(bytes=_solid_page((255, 0, 0)), index=0, width=50, height=50),
        PageBlob(bytes=_solid_page((0, 255, 0)), index=1, width=50, height=50),
    ]
    out = tmp_path / "ch001.cbz"
    result = packager.build(pages, sample_info, out)
    assert result.path == out
    assert out.exists()
    assert result.size_bytes > 0
    assert result.page_count == 2
    assert len(result.sha256) == 64  # hex sha-256


def test_cbz_contains_comicinfo_and_paginated_images(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    pages = [
        PageBlob(bytes=_solid_page((10, 20, 30)), index=0, width=50, height=50),
        PageBlob(bytes=_solid_page((40, 50, 60)), index=1, width=50, height=50),
        PageBlob(bytes=_solid_page((70, 80, 90)), index=2, width=50, height=50),
    ]
    out = tmp_path / "ch001.cbz"
    packager.build(pages, sample_info, out)

    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
    assert names == ["ComicInfo.xml", "page001.jpg", "page002.jpg", "page003.jpg"]


def test_comicinfo_xml_inside_cbz_is_valid_xml(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    pages = [PageBlob(bytes=_solid_page((1, 1, 1)), index=0, width=50, height=50)]
    out = tmp_path / "ch001.cbz"
    packager.build(pages, sample_info, out)
    with zipfile.ZipFile(out, "r") as zf:
        xml = zf.read("ComicInfo.xml")
    from xml.etree import ElementTree as ET
    root = ET.fromstring(xml)
    assert root.tag == "ComicInfo"
    assert root.findtext("Title") == "Test Chapter 1"
    assert root.findtext("PageCount") == "1"


# ---------------------------------------------------------- golden hash test


def test_rebuild_produces_identical_sha256(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    """Two builds from the same input must produce the same bytes.

    This is the property that makes `chapters.sha256` stable across
    re-packs — and the foundation of our idempotent re-download.
    """
    pages = [
        PageBlob(bytes=_solid_page((123, 45, 67)), index=0, width=50, height=50),
        PageBlob(bytes=_solid_page((11, 22, 33)), index=1, width=50, height=50),
        PageBlob(bytes=_solid_page((99, 88, 77)), index=2, width=50, height=50),
    ]
    out_a = tmp_path / "a.cbz"
    out_b = tmp_path / "b.cbz"
    r_a = packager.build(pages, sample_info, out_a)
    r_b = packager.build(pages, sample_info, out_b)
    assert r_a.sha256 == r_b.sha256
    assert r_a.size_bytes == r_b.size_bytes

    # The on-disk bytes must be identical too.
    assert out_a.read_bytes() == out_b.read_bytes()


def test_zip_entry_timestamps_are_pinned_to_1980(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    pages = [PageBlob(bytes=_solid_page((0, 0, 0)), index=0, width=50, height=50)]
    out = tmp_path / "ch001.cbz"
    packager.build(pages, sample_info, out)
    with zipfile.ZipFile(out, "r") as zf:
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0), info.filename


# ----------------------------------------------------------------- overrides


def test_page_count_in_xml_matches_zip(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    """Even if the caller lied in `page_count`, the packager fixes it."""
    sample_info = ComicInfo(**{**sample_info.__dict__, "page_count": 999})
    pages = [PageBlob(bytes=_solid_page((0, 0, 0)), index=i, width=50, height=50) for i in range(4)]
    out = tmp_path / "ch001.cbz"
    r = packager.build(pages, sample_info, out)
    assert r.page_count == 4
    with zipfile.ZipFile(out, "r") as zf:
        from xml.etree import ElementTree as ET
        assert ET.fromstring(zf.read("ComicInfo.xml")).findtext("PageCount") == "4"


def test_zero_padded_filename_width(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    """page_count=12 => 'page01.jpg' … 'page12.jpg'? No, 3 digits.

    The plan says "max(3, len(str(page_count)))". For 12 pages that's
    3, so `page001.jpg` … `page012.jpg`. For 1234 pages, 4 digits.
    """
    # 12 pages.
    pages = [PageBlob(bytes=_solid_page((i, i, i)), index=i, width=10, height=10) for i in range(12)]
    out = tmp_path / "ch.cbz"
    packager.build(pages, sample_info, out)
    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
    # First non-ComicInfo entry.
    page_names = [n for n in names if n.startswith("page")]
    assert page_names[0] == "page001.jpg"
    assert page_names[-1] == "page012.jpg"
    # All have the same width.
    widths = {len(n) for n in page_names}
    assert widths == {len("page001.jpg")}


def test_four_digit_padding_for_1000_plus_pages(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    pages = [
        PageBlob(bytes=_solid_page((0, 0, 0)), index=i, width=10, height=10)
        for i in range(1000)
    ]
    out = tmp_path / "ch.cbz"
    r = packager.build(pages, sample_info, out)
    assert r.page_count == 1000
    with zipfile.ZipFile(out, "r") as zf:
        first, last = "page0001.jpg", "page1000.jpg"
        names = set(zf.namelist())
    assert first in names
    assert last in names


# ------------------------------------------------------- atomic-write / errors


def test_empty_pages_raises(packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo) -> None:
    with pytest.raises(ValueError, match="zero pages"):
        packager.build([], sample_info, tmp_path / "x.cbz")


def test_atomic_write_leaves_no_tmp_file(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    pages = [PageBlob(bytes=_solid_page((0, 0, 0)), index=0, width=10, height=10)]
    out = tmp_path / "ch.cbz"
    packager.build(pages, sample_info, out)
    # No .tmp sibling should remain.
    siblings = [p.name for p in tmp_path.iterdir()]
    assert ".tmp" not in [s.split(".")[-1] for s in siblings]
    assert "ch.cbz" in siblings


def test_overwrite_existing_cbz(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    out = tmp_path / "ch.cbz"
    pages_a = [PageBlob(bytes=_solid_page((0, 0, 0)), index=0, width=10, height=10)]
    pages_b = [PageBlob(bytes=_solid_page((255, 255, 255)), index=0, width=10, height=10)]
    r1 = packager.build(pages_a, sample_info, out)
    r2 = packager.build(pages_b, sample_info, out)
    # Different content, different SHA — but no exception, single file on disk.
    assert r1.sha256 != r2.sha256
    assert out.exists()
    siblings = list(tmp_path.iterdir())
    assert len(siblings) == 1


# ------------------------------------------------------------- input formats


def test_png_input_is_converted_to_jpeg(
    packager: CbzPackager, tmp_path: Path, sample_info: ComicInfo,
) -> None:
    png = _make_png((10, 10))
    pages = [PageBlob(bytes=png, index=0, width=10, height=10)]
    out = tmp_path / "ch.cbz"
    packager.build(pages, sample_info, out)
    with zipfile.ZipFile(out, "r") as zf:
        raw = zf.read("page001.jpg")
    # JPEG magic.
    assert raw[:3] == b"\xff\xd8\xff"


def _make_png(size: tuple[int, int]) -> bytes:
    img = Image.new("RGB", size, (128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
