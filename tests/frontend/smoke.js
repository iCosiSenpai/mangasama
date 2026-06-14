#!/usr/bin/env node
/**
 * Smoke test for the frontend integration.
 *
 * Assumes the FastAPI backend is already running on http://localhost:8000.
 * Exits 0 iff:
 *   - GET /api/health returns 200, AND
 *   - GET /api/libraries returns 200 with at least one library.
 *
 * Usage: node tests/frontend/smoke.js
 */

const BASE = process.env.MANGASAMA_BASE || 'http://localhost:8000'

async function getJson(path) {
  const url = new URL(path, BASE)
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  const text = await res.text()
  let json
  try {
    json = JSON.parse(text)
  } catch {
    json = text
  }
  return { status: res.status, json }
}

function pad(s, n) {
  s = String(s)
  return s.length >= n ? s : ' '.repeat(n - s.length) + s
}

function ok(msg) {
  console.log(`  ✓ ${msg}`)
}

function fail(msg) {
  console.error(`  ✗ ${msg}`)
  process.exitCode = 1
}

async function main() {
  console.log(`Smoke test against ${BASE}\n`)

  // 1. Health
  let health
  try {
    health = await getJson('/api/health')
  } catch (e) {
    console.error(`Cannot reach ${BASE}: ${e.message}`)
    console.error('Start the backend with: python -m uvicorn app.main:app --port 8000')
    process.exit(1)
  }

  if (health.status !== 200) {
    fail(`GET /api/health returned ${health.status}`)
  } else {
    ok(`GET /api/health -> 200 (${health.json.app} ${health.json.version}, uptime ${health.json.uptime_seconds}s)`)
  }

  // 2. Libraries
  const libs = await getJson('/api/libraries')
  if (libs.status !== 200) {
    fail(`GET /api/libraries returned ${libs.status}: ${JSON.stringify(libs.json).slice(0, 200)}`)
  } else if (!Array.isArray(libs.json)) {
    fail(`GET /api/libraries did not return an array: ${JSON.stringify(libs.json).slice(0, 200)}`)
  } else if (libs.json.length === 0) {
    fail('GET /api/libraries returned [] (need at least 1 library to validate the UI).')
    console.error('  Hint: create one via Swagger at /api/docs or python -m app.cli library-add ...')
  } else {
    ok(`GET /api/libraries -> 200 (${libs.json.length} libraries)`)
    const rows = libs.json.map((l) => [
      l.id,
      l.name,
      l.type,
      l.series_count,
      (l.providers || []).join(','),
      l.italian_priority ? 'true' : 'false',
    ])
    const headers = ['#', 'name', 'type', 'series', 'providers', 'it_first']
    const widths = headers.map((h, i) =>
      Math.max(h.length, ...rows.map((r) => String(r[i] ?? '').length)),
    )
    const fmt = (cells) => cells.map((c, i) => pad(c, widths[i])).join(' | ')
    const sep = widths.map((w) => '-'.repeat(w)).join('-+-')
    console.log()
    console.log(fmt(headers))
    console.log(sep)
    for (const r of rows) console.log(fmt(r))
  }

  if (process.exitCode) {
    console.error('\nSmoke FAILED')
  } else {
    console.log('\nSmoke OK')
  }
}

main().catch((e) => {
  console.error('Smoke crashed:', e)
  process.exit(1)
})
