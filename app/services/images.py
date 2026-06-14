"""Image conversion helpers.

The scraper gives us page bytes in whatever format the source serves
(WebP, PNG, JPEG, sometimes AVIF). The packager wants everything as
JPEG q85 (default) so the resulting CBZ is smaller and reads everywhere
(Komga, Kavita, Moon+ Reader, …).

`convert_to_jpg` is the single conversion primitive. It is pure:
bytes in, bytes out. No disk I/O. The packager wraps it in a streaming
context.

For tests we keep it simple: no alpha channel gymnastics, no
chroma-subsampling magic. The default `quality=85`, `optimize=True`,
`progressive=True` matches the plan and keeps the byte stream
deterministic for the golden-hash test.
"""

from __future__ import annotations

import io
from typing import Final

from PIL import Image

# Pillow's JPEG encoder doesn't expose a knob for "I want byte-identical
# output across runs" because EXIF / color profile metadata can change.
# We strip everything and let Pillow produce the canonical output.
DEFAULT_JPG_QUALITY: Final[int] = 85


class ImageConversionError(Exception):
    """Raised when a byte blob cannot be decoded as an image."""


def _normalize_mode(img: Image.Image) -> Image.Image:
    """Convert RGBA / P / LA to RGB so JPEG encoding is well-defined.

    We paste onto a white background (alpha-compositing) so transparent
    pages (rare in manga, common in covers) end up sensible.
    """
    mode = img.mode
    if mode == "RGB":
        return img
    if mode in ("RGBA", "LA") or (mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def convert_to_jpg(
    data: bytes,
    *,
    quality: int = DEFAULT_JPG_QUALITY,
) -> bytes:
    """Decode `data` and re-encode as JPEG.

    Args:
        data: source bytes (any format Pillow can read).
        quality: 1-95 JPEG quality (default 85).

    Returns:
        Encoded JPEG bytes (no EXIF, no ICC profile, no metadata).

    Raises:
        ImageConversionError: on decode failure.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()  # force full read so failures surface here
            rgb = _normalize_mode(img)
            buf = io.BytesIO()
            rgb.save(
                buf,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )
            return buf.getvalue()
    except Exception as e:  # PIL raises a zoo of exceptions
        raise ImageConversionError(f"Cannot convert image: {e}") from e


def is_jpeg(data: bytes) -> bool:
    """Cheap magic-byte check; used to skip re-encoding already-JPEG pages."""
    return data[:3] == b"\xff\xd8\xff"
