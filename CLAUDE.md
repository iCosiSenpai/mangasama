# CLAUDE.md — MangaSama AI assistant instructions

> **READ THIS FILE FIRST** whenever you start a new Claude Code session on
> the MangaSama project. The detailed roadmap is in `ROADMAP.md`.

## What this project is

**MangaSama** is a Docker-based, Italian-first manga downloader with a
follow/like scheduler, multi-source scrapers, CBZ+ComicInfo output, OPDS 1.2
catalog, and a Vue 3 UI. Built from scratch in Python 3.12 + FastAPI + SQLite,
single Docker container, no Lua, no komf.

**Project root**: `F:\dev\mangadownloader` (Windows).

## Mandatory session-start procedure

1. **Read `ROADMAP.md`** in full. It's the executive view: what's done,
   what's next, conventions, the file map, the run-the-project cheat sheet,
   the step-by-step checklist.
2. **Read the full plan** at
   `.claude/plans/g-dev-mangadownloader-voglio-creare-floating-hartmanis.md`
   for architectural detail when ROADMAP.md points you to it.
3. **Identify the next step** as the first `[ ]` (or `[~]`) item in
   ROADMAP.md §1.
4. **Run the smoke test** to confirm the project is healthy:
   ```
   & "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_smoke.py -v
   ```
5. **State the plan** for the next step in plain text before writing any code.
6. **Update the ROADMAP.md checklist** (`[ ]` → `[~]` → `[x]`) as the work
   progresses. Append to §9 (open issues) and §10 (out-of-plan work) as needed.

## Hard rules — never break these

These are the project's **architectural invariants** (also in ROADMAP.md §3):

1. **No Lua anywhere.** All scrapers are pure Python (`httpx` + `parsel` + `lxml`).
2. **No komf in the stack.** Metadata is our own: `AniListProvider` +
   `MangaDexProvider` + dormant `GoogleBooksProvider`. Do not add a `komf`
   container to the compose or call its API.
3. **Single Docker container.** No multi-service compose unless explicitly
   added later. `/data` and `/config` are the only persistent volumes.
4. **Italian-first.** For any series with both `it` and `en` translations,
   `it` wins. `library.italian_priority` is a hard default.
5. **Idempotency by `(source_provider, source_id, language)`.** A chapter
   downloaded twice is the same DB row. The DB unique constraint enforces this.
6. **ComicInfo.xml v2.1 is mandatory in every CBZ.** Use `ComicInfoBuilder`.
7. **Zero-padded page names** (`page001.jpg`, …) with width
   `max(3, len(str(pages_count)))`.
8. **Deterministic ZIPs**: every entry timestamped `(1980, 1, 1, 0, 0, 0)`.
9. **Domain registry over hardcoded URLs.** Edit `config/sources.yaml`,
   not code.
10. **Content types v1**: `manga | manhua | manhwa` only. Reject
    `novel | comic | webtoon` at the API boundary with a 400.
11. **The 12-table schema is fixed.** Adding columns is fine; splitting
    tables needs a discussion.
12. **App name is MangaSama** (Italian, not English "MangaDownloader").
    Project name: `mangasama`. Docker image: `mangasama/mangasama`.

## Where things live

See **ROADMAP.md §2** for the project tree and **§4** for the critical file
map. Don't load every file; load only the ones the next step needs (the
file map names them).

## Python environment

Use the system Python directly (Windows PATH is not set up cleanly here):

```
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -e ".[dev]"
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -v
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m alembic upgrade head
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn app.main:app --reload
& "C:\Users\cosia\AppData\Local\Programs\Python\Python312\python.exe" -m app.cli <command>
```

## When something is unclear

- **First**, check ROADMAP.md (this session's source of truth).
- **Then**, check the full plan at `.claude/plans/g-dev-mangadownloader-voglio-creare-floating-hartmanis.md`.
- **Then**, read the relevant existing code before writing new code.
- **Only then** ask the user.

## When the user requests something outside the plan

Add it to **ROADMAP.md §10** ("Out-of-plan work") and flag it explicitly
before implementing. Don't silently expand scope.
