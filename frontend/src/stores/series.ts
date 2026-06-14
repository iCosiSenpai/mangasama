import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { client, apiError } from '@/api/client'
import type { SeriesCreate, SeriesListItem } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

/**
 * Series list state, keyed by library. `load(libraryId)` is idempotent; the
 * store only fetches when the cached list for that library is empty.
 *
 * `addFromCandidate` is the search→add flow: it calls `POST /api/series`
 * with the provider + external_id from a `SearchCandidate`, then re-loads
 * the library's list.
 */
export const useSeriesStore = defineStore('series', () => {
  const items: Ref<SeriesListItem[]> = ref([])
  const libraryId: Ref<number | null> = ref(null)
  const status: Ref<Status> = ref('idle')
  const error: Ref<string | null> = ref(null)
  const adding: Ref<boolean> = ref(false)

  const followedCount = computed(() => items.value.filter((s) => s.followed).length)

  async function load(id: number, force = false): Promise<void> {
    if (!force && libraryId.value === id && status.value === 'ready') return
    libraryId.value = id
    status.value = 'loading'
    error.value = null
    try {
      const { data } = await client.get<SeriesListItem[]>('/api/series', {
        params: { library_id: id, limit: 200 },
      })
      items.value = data
      status.value = 'ready'
    } catch (e) {
      error.value = apiError(e)
      status.value = 'error'
    }
  }

  function reset(): void {
    items.value = []
    libraryId.value = null
    status.value = 'idle'
    error.value = null
  }

  async function addFromCandidate(opts: {
    libraryId: number
    provider: string
    externalId: string
    runMetadataRefresh?: boolean
  }): Promise<SeriesListItem> {
    adding.value = true
    try {
      const body: SeriesCreate = {
        library_id: opts.libraryId,
        provider: opts.provider,
        external_id: opts.externalId,
        language: 'it',
        run_metadata_refresh: opts.runMetadataRefresh ?? true,
      }
      const { data } = await client.post('/api/series', body)
      // `data` is a full SeriesRead; coerce to a list-item shape.
      // The list reload picks up the new row from the backend.
      await load(opts.libraryId, true)
      return data as unknown as SeriesListItem
    } finally {
      adding.value = false
    }
  }

  async function setFollowed(seriesId: number, followed: boolean): Promise<void> {
    const url = followed
      ? `/api/series/${seriesId}/follow`
      : `/api/series/${seriesId}/unfollow`
    await client.post(url)
    // Optimistic local update — the next list load (or refetch) is the
    // source of truth. The full SeriesRead isn't returned from
    // /follow, so we just patch the list item.
    const idx = items.value.findIndex((s) => s.id === seriesId)
    if (idx >= 0) {
      items.value[idx] = { ...items.value[idx], followed }
    }
  }

  return {
    items,
    libraryId,
    status,
    error,
    adding,
    followedCount,
    load,
    reset,
    addFromCandidate,
    setFollowed,
  }
})
