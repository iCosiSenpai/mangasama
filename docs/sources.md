# MangaSama — Sources

Sources (sites) and their domains live in **`config/sources.yaml`** — the single source of truth.
The `DomainRegistry` loads it and, together with the `domain_health` table, decides which domain
of a source to use at any moment. Scrapers never hardcode URLs.

## Registered sources (v1)

| Source | Tier | Primary domain | Alternates | Rate limit (rpm) | Cloudflare/cookie | Enabled | Content |
|---|---|---|---|---|---|---|---|
| **mangadex** | 1 | `api.mangadex.org` | — | 40 | no | ✅ | manga, manhua, manhwa |
| **mangaworld** | 1 | `mangaworld.mx` | `mangaworldacg.com`, `mangaworld.io` | 20 | CF-fronted | ✅ | manga, manhua, manhwa |
| **mangaeden** | 1 | `mangaeden.com` | — | 60 | no | ❌ defunct | manga |
| **bato** | 2 | `bato.to` | — | 20 | CF-fronted | ✅ | manga, manhua, manhwa |
| **mangakakalot** | 2 | `mangakakalot.com` | `manganato.com` | 30 | CF-fronted | ✅ | manga |
| **mangapark** | 2 | `mangapark.org` | `mangapark.io`, `mangapark.com` | 20 | cookie recommended | ❌ opt-in | manga, manhua, manhwa |

Notes:
- **MangaEden** is offline as of 2026-06 (domain redirects elsewhere); kept `enabled: false` for
  forward-compat in case a mirror reappears. **MangaWorld.mx** is the de-facto Italian-first Tier-1.
- **MangaDex** is multi-language; Italian comes from scanlation translations (we ask `it`, then `en`).
- **Bato / MangaKakalot / MangaPark** are Cloudflare-fronted; without a solver they can fail health
  checks and individual fetches → the orchestrator falls back to the next source. See
  *Cloudflare* below.

Per-scraper rate limits come from `config/default.yaml` (`scrapers.per_scraper.*`); the global
default is `DEFAULT_RATE_LIMIT_RPM` (30). Tier-2 scrapers are toggled with env flags:
`SCRAPER_MANGAPARK_ENABLED`, `SCRAPER_BATO_ENABLED`, `SCRAPER_MANGAKAKALOT_ENABLED`.

## How domain selection + health works

1. `config/sources.yaml` lists a `primary` and ordered `alternates` per source.
2. On startup, `app/db/init.py` seeds a `domain_health` row for every enabled `(source, domain)`
   (idempotent — existing rows with failures are preserved).
3. The `domain_health` cron (`app/services/health.py`, every `SCHEDULER_DOMAIN_HEALTH_MIN` min)
   pings each domain's `health_check_path` with a short-timeout, no-retry client and records
   success/failure. **3 consecutive failures** flip `healthy=False`.
4. `DomainRegistry.pick_domain(source)` returns the primary if healthy, otherwise the
   lowest-`fail_count` healthy alternate (falling back to the least-bad domain as a last resort).
5. Live fetches also call `record_success`/`record_failure`, so health reflects real traffic too.

Admin endpoints: `POST /api/settings/providers/health/check` (ping now),
`POST /api/settings/providers/{source}/reset` (clear a source's failures),
`GET /api/settings/providers/health` (snapshot). The UI surfaces this in **Settings**.

## Adding or rotating a source / domain

Edit `config/sources.yaml` — no code change needed:

```yaml
sources:
  mangaworld:
    display_name: MangaWorld
    tier: 1
    primary: mangaworld.mx
    alternates: [mangaworldacg.com, mangaworld.io]   # add/rotate domains here
    scheme: https
    health_check_path: /
    enabled: true
    content_types: [manga, manhua, manhwa]
```

On next startup the new `(source, domain)` pairs are seeded into `domain_health`; the health cron
and `pick_domain` pick them up automatically. Adding a brand-new *scraper* (not just a domain)
means dropping a `BaseScraper` subclass into `app/scrapers/` (auto-discovered by the registry).

## Cloudflare

If a domain returns a Cloudflare challenge the scraper raises `BlockedByCloudflare` and the
orchestrator falls back to the next source. A solver can be wired via `CLOUDFLARE_SOLVER`
(`playwright` or `flaresolverr`, with `FLARESOLVERR_URL`). *The solver dispatch itself is on the
roadmap (not yet implemented); today CF-fronted domains simply fail over.*
