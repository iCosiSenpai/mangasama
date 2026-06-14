# MangaSama — ComicInfo.xml

Every CBZ contains a `ComicInfo.xml` (v2.1) as its first entry, built only by
`ComicInfoBuilder` (`app/services/comicinfo.py`). The field values are mapped from the series +
scraped chapter in `app/services/downloader.py::_build_comic_info`. Schema reference:
<https://anansi-project.github.io/docs/comicinfo/schemas/v2.1>.

## Field mapping

| ComicInfo field | Source in MangaSama | Notes |
|---|---|---|
| `Title` | `chapter.title` | The chapter's own title (may be empty). |
| `Series` | `series.title` | |
| `Number` | `chapter.number` | e.g. `"114"`, `"12.5"`. |
| `Volume` | `chapter.volume_number` | Omitted when empty/`0`. |
| `Summary` | `series.summary` | |
| `LanguageISO` | `chapter.language` | BCP-47 (`it`, `en`, …). |
| `Writer`, `Penciller`, `Inker`, `Colorist`, `Letterer`, `CoverArtist`, `Editor` | `series.authors` grouped by `role` | Comma-joined per role. |
| `Translator` | `chapter.scanlation_group` | Scanlation team, when provided. |
| `Genre` | `series.genres` | Comma-joined. |
| `Tags` | `series.tags` | Comma-joined. |
| `Web` | `chapter.url` | Source URL of the chapter. |
| `Publisher` | — | No column in v1 (reserved). |
| `Manga` | derived from `library.type` | `YesAndRightToLeft` for manga/manhwa; `Yes` (left-to-right) for manhua. |
| `StoryArc` | `series.title` | Helps Komga/Kavita group chapters. |
| `StoryArcNumber` | `{volume}.{number}` | Zero-padded chapter portion for stable sort. |
| `PageCount` | number of packed pages | Always matches the archive. |
| `<Pages>` | one `<Page Image=N ImageWidth=W ImageHeight=H/>` per page | Geometry filled when known. |

Empty fields are omitted (no empty `<Tag/>`). Output is UTF-8, no BOM, XML characters escaped.

## CBZ packaging guarantees

- **Deterministic ZIP**: every entry is timestamped `(1980, 1, 1, 0, 0, 0)`, so re-packing the
  same input yields byte-identical output (stable SHA-256, good for dedup/backups).
- **Page names** are `pageNNN.jpg`, zero-padded to `max(3, len(str(page_count)))` digits, so
  lexicographic order = reading order.
- `ComicInfo.xml` is stored `ZIP_DEFLATED`; page JPEGs are `ZIP_STORED` (already compressed).
- Pages are converted to JPEG (quality from `library.jpg_quality`, default 85); the CBZ is written
  to a temp file and atomically renamed onto the destination.
- The chapter row records `cbz_size` and `cbz_sha256`; each page row records its `sha256`.
