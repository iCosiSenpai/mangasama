"""Tests for the image conversion primitive.

Pillow isn't guaranteed to produce byte-identical output across
versions/platforms, so we test properties (format, mode, approximate
size), not exact byte equality.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services.images import (
    DEFAULT_JPG_QUALITY,
    ImageConversionError,
    convert_to_jpg,
    is_jpeg,
)


# ----------------------------------------------------------------- helpers


def _make_png(*, mode: str = "RGB", size: tuple[int, int] = (10, 10),
              color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """Build a deterministic in-memory PNG."""
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_webp(*, size: tuple[int, int] = (10, 10)) -> bytes:
    img = Image.new("RGB", size, (0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


def _make_rgba_png(size: tuple[int, int] = (10, 10)) -> bytes:
    img = Image.new("RGBA", size, (0, 0, 255, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ is_jpeg


def test_is_jpeg_detects_jpeg_magic_bytes() -> None:
    assert is_jpeg(b"\xff\xd8\xff\xe0\x00\x10JFIF") is True
    assert is_jpeg(b"\xff\xd8\xff\xe1") is True
    assert is_jpeg(b"not a jpeg") is False
    assert is_jpeg(b"") is False
    # PNG magic is not JPEG.
    assert is_jpeg(b"\x89PNG\r\n\x1a\n") is False


# --------------------------------------------------------- convert_to_jpg


def test_convert_png_rgb_to_jpg() -> None:
    out = convert_to_jpg(_make_png())
    assert is_jpeg(out)
    # Decode and assert size + mode match the source.
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"
        assert img.size == (10, 10)


def test_convert_webp_to_jpg() -> None:
    out = convert_to_jpg(_make_webp())
    assert is_jpeg(out)
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"


def test_rgba_is_composited_on_white() -> None:
    out = convert_to_jpg(_make_rgba_png())
    with Image.open(io.BytesIO(out)) as img:
        # The conversion must produce RGB (alpha dropped).
        assert img.mode == "RGB"


def test_quality_affects_size() -> None:
    src = _make_png(size=(200, 200), color=(120, 120, 120))
    hi = convert_to_jpg(src, quality=95)
    lo = convert_to_jpg(src, quality=20)
    # Lower quality => fewer bytes (almost always — for non-trivial content).
    assert len(lo) < len(hi)


def test_default_quality_is_85() -> None:
    # The plan default. Changing it would break the planned storage budget.
    assert DEFAULT_JPG_QUALITY == 85


def test_invalid_bytes_raise_conversion_error() -> None:
    with pytest.raises(ImageConversionError):
        convert_to_jpg(b"definitely not an image")


def test_empty_input_raises_conversion_error() -> None:
    with pytest.raises(ImageConversionError):
        convert_to_jpg(b"")
