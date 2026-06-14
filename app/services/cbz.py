"""CBZ packager.

A CBZ is just a ZIP with the `.cbz` extension. The conventions we follow:

  - All entries use the fixed timestamp (1980, 1, 1, 0, 0, 0) so a
    re-packaged chapter produces the same bytes. This is what makes
    our SHA-256 "golden hash" test deterministic.
  - Page images are stored as `ZIP_STORED` (no compression) because
    they're already JPEG and re-compressing wastes CPU. The single
    `ComicInfo.xml` is stored as `ZIP_DEFLATED` (level 6) — it's
    small and benefits from compression.
  - Page filenames are `pageNNN.jpg` where NNN is zero-padded to
    `max(3, len(str(page_count)))` digits, e.g. `page001.jpg` …
    `page042.jpg` for 42 pages, `page1000.jpg` for 1000.
  - The archive is written to a temp file and atomically renamed onto
    the destination, so a crashed packager never leaves a half-written
    file at the final path.

The packager is the only thing that touches disk; everything upstream
(orchestrator, downloader) works with bytes. The output is a
`CbzResult` value object.
"""

from __future__ import annotations

import os
import time
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED

import structlog

from app.core.hashing import sha256_bytes
from app.core.paths import ensure_dir
from app.services.comicinfo import ComicInfo, build_xml
from app.services.images import DEFAULT_JPG_QUALITY, convert_to_jpg

logger = structlog.get_logger("mangasama.services.cbz")

#: The single deterministic timestamp used for every ZIP entry.
#: zipfile expects (year, month, day, hour, minute, second).
_FIXED_TS: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class PageBlob:
    """A single page's bytes + its ComicInfo <Page> geometry."""

    bytes: bytes
    index: int                       # 0-based
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class CbzResult:
    """The output of a successful pack."""

    path: Path
    sha256: str
    size_bytes: int
    page_count: int
    duration_ms: int


class CbzPackager:
    """Build a single CBZ from page bytes + ComicInfo metadata."""

    def build(
        self,
        pages: Sequence[PageBlob],
        comic_info: ComicInfo,
        out_path: Path,
    ) -> CbzResult:
        if not pages:
            raise ValueError("Cannot package a CBZ with zero pages")
        out_path = Path(out_path)
        ensure_dir(out_path.parent)
        if out_path.exists():
            # Caller asked us to overwrite — fine, but log it.
            logger.info("cbz.overwrite", path=str(out_path))

        # Patch the page count into ComicInfo so the XML always matches
        # what's in the archive.
        comic_info = ComicInfo(
            **{**comic_info.__dict__, "page_count": len(pages)}
        )

        xml_bytes = build_xml(comic_info)
        # We pin every entry's timestamp, so the central directory is
        # byte-deterministic for the same input + config.
        info = zipfile.ZipInfo
        pad = max(3, len(str(len(pages))))

        started = time.perf_counter()
        buf = BytesIO()
        with zipfile.ZipFile(
            buf, "w", compression=ZIP_DEFLATED, allowZip64=True,
        ) as zf:
            # ComicInfo.xml first — readers are happy with that order and
            # the SHA stays deterministic.
            zi = info("ComicInfo.xml", date_time=_FIXED_TS)
            zi.compress_type = ZIP_DEFLATED
            zf.writestr(zi, xml_bytes)

            for p in pages:
                page_bytes = convert_to_jpg(
                    p.bytes, quality=DEFAULT_JPG_QUALITY,
                )
                # Filenames are 1-based (page001.jpg) to match reader
                # expectations; the `index` field stays 0-based.
                name = f"page{p.index + 1:0{pad}d}.jpg"
                zi = info(name, date_time=_FIXED_TS)
                zi.compress_type = ZIP_STORED  # already-compressed JPEG
                zf.writestr(zi, page_bytes)

        data = buf.getvalue()
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        with tmp.open("wb") as f:
            f.write(data)
        os.replace(tmp, out_path)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        digest = sha256_bytes(data)
        result = CbzResult(
            path=out_path,
            sha256=digest,
            size_bytes=len(data),
            page_count=len(pages),
            duration_ms=elapsed_ms,
        )
        logger.info(
            "cbz.built", path=str(out_path), pages=len(pages),
            size=len(data), sha256=digest, ms=elapsed_ms,
        )
        return result
