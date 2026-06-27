/**
 * Types mirrored 1:1 from the Pydantic schemas in `app/schemas/`.
 * Keep this file hand-curated until we generate from OpenAPI in a later step.
 */

export type LibraryType = 'manga' | 'manhua' | 'manhwa'

export type LibraryFolderStrategy =
  | 'series_volume_chapter'
  | 'series_volume'
  | 'chapter_flat'
  | 'onefile_per_volume'

export interface LibraryRead {
  id: number
  name: string
  type: LibraryType
  root_path: string
  folder_strategy: LibraryFolderStrategy
  cover_strategy: string
  providers: string[]
  italian_priority: boolean
  follow_interval_hours: number
  jpg_quality: number
  series_count: number
  created_at: string
  updated_at: string
  deleted: boolean
}

/** Body for `POST /api/libraries` (mirror of `LibraryCreate`). */
export interface LibraryCreate {
  name: string
  type: LibraryType
  root_path: string
  folder_strategy: LibraryFolderStrategy
  cover_strategy?: string
  providers: string[]
  italian_priority: boolean
  follow_interval_hours: number
  jpg_quality: number
}

/** Body for `PATCH /api/libraries/{id}` — all fields optional. */
export type LibraryUpdate = Partial<LibraryCreate>

export interface ProviderHealth {
  provider: string
  healthy: boolean
  last_ok: string | null
  last_fail: string | null
  fail_count: number
  last_status_code: number | null
}

export interface HealthSnapshot {
  providers: ProviderHealth[]
}

export interface FollowSummary {
  series_id: number
  library_id: number
  title: string
  followed_at: string | null
  last_checked_at: string | null
  last_status: string | null
  last_new_chapters: number | null
}

export interface SettingsPatch {
  log_level?: string
  default_rate_limit_rpm?: number
}

export interface SetupAdmin {
  username: string
  password: string
}

export interface SetupPayload {
  admin: SetupAdmin
  libraries: LibraryCreate[]
  settings?: Record<string, unknown>
}

export interface SetupStatus {
  setup_required: boolean
  has_users: boolean
  has_libraries: boolean
  default_settings: Record<string, unknown>
}

export interface AdminSettings {
  log_level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
  backup_enabled: boolean
  backup_retention_days: number
  default_rate_limit_rpm: number
  scraper_mangapark_enabled: boolean
  scraper_bato_enabled: boolean
  scraper_mangakakalot_enabled: boolean
  scheduler_follow_interval_min: number
  scheduler_domain_health_min: number
  scheduler_job_retention_days: number
  cloudflare_solver: '' | 'playwright' | 'flaresolverr'
  flaresolverr_url: string
  google_books_enabled: boolean
  mangaeden_enabled: boolean
}

export type AdminSettingsPatch = Partial<AdminSettings>

export interface LibraryStats {
  series_count: number
  chapters_count: number
  downloaded_chapters: number
  total_bytes: number
}

export interface EffectiveSettings {
  app_name: string
  version: string
  log_level: string
  data_dir: string
  config_dir: string
  db_url: string
  library_defaults: Record<string, unknown>
  known_scrapers: string[]
  enabled_scrapers: string[]
}

export interface SearchCandidate {
  provider: string
  external_id: string
  url: string | null
  title: string
  alt_titles: string[]
  year: number | null
  cover_url: string | null
  language: string | null
  type: string | null
  score: number
  is_italian_available: boolean
}

export interface SearchRequest {
  library_id: number
  query: string
  providers?: string[] | null
  languages?: string[]
  limit_per_provider?: number
}

export interface SearchResponse {
  query: string
  library_id: number
  providers_used: string[]
  candidates: SearchCandidate[]
}

export interface SeriesExternalIdRead {
  provider: string
  external_id: string
  url: string | null
  fetched_at: string | null
}

export interface SeriesListItem {
  id: number
  library_id: number
  title: string
  sort_title: string | null
  year: number | null
  status: string | null
  cover_path: string | null
  language: string | null
  followed: boolean
  external_ids: SeriesExternalIdRead[]
}

export interface SeriesAuthorRead {
  role: string
  name: string
}

/** Mirrors `app/schemas/series.py:SeriesRead`. */
export interface SeriesRead {
  id: number
  library_id: number
  title: string
  sort_title: string | null
  alt_titles: string[]
  status: string | null
  summary: string | null
  year: number | null
  language: string | null
  cover_path: string | null
  source_priority: string[]
  followed: boolean
  followed_at: string | null
  last_checked_at: string | null
  created_at: string
  updated_at: string
  deleted: boolean
  external_ids: SeriesExternalIdRead[]
  authors: SeriesAuthorRead[]
  genres: string[]
  tags: string[]
  volume_count: number
}

/** Mirrors `app/schemas/chapter.py:ChapterListItem`. */
export interface ChapterListItem {
  id: number
  volume_id: number
  number: string
  title: string | null
  language: string
  pages_count: number | null
  downloaded_at: string | null
  cbz_size: number | null
  source_provider: string
}

export interface SeriesCreate {
  library_id: number
  provider: string
  external_id: string
  language?: string | null
  run_metadata_refresh?: boolean
}

export type JobStatus = 'pending' | 'running' | 'done' | 'error'

/** Mirrors `app/schemas/job.py:JobRead`. */
export interface JobRead {
  id: number
  job_type: string
  provider: string | null
  status: string
  progress: number
  message: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
}

/** SSE frame published by the download workers (`downloader.DownloadQueue._publish`). */
export interface JobEvent {
  id: number
  job_type: string
  provider: string | null
  status: string
  progress: number
  error: string | null
  series_id?: number
  source_id?: string
  language?: string
}

/** Normalized API error shape (mirrors `app/api/exception_handlers.py`). */
export interface ApiErrorPayload {
  status: number
  detail: string
  type: string
  errors?: unknown
  raw: unknown
}
