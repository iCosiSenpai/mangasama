import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { apiError, client } from '@/api/client'
import type { LibraryCreate, LibraryRead, LibraryUpdate } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

/**
 * Single store for the libraries list. `load()` is idempotent and safe to
 * call from multiple `onMounted` hooks (sidebar, library list view);
 * mutations re-fetch so the list (and the sidebar) stay in sync.
 */
export const useLibrariesStore = defineStore('libraries', () => {
  const items: Ref<LibraryRead[]> = ref([])
  const status: Ref<Status> = ref('idle')
  const error: Ref<string | null> = ref(null)

  const byId = computed<Record<number, LibraryRead>>(() =>
    Object.fromEntries(items.value.map((l) => [l.id, l])),
  )

  const totalSeries = computed<number>(() =>
    items.value.reduce((sum, l) => sum + l.series_count, 0),
  )

  async function _fetch(): Promise<void> {
    status.value = 'loading'
    error.value = null
    try {
      const { data } = await client.get<LibraryRead[]>('/api/libraries')
      items.value = data
      status.value = 'ready'
    } catch (e) {
      error.value = apiError(e)
      status.value = 'error'
    }
  }

  async function load(force = false): Promise<void> {
    // Skip the network roundtrip if we already have a fresh copy.
    if (!force && (status.value === 'loading' || status.value === 'ready')) return
    await _fetch()
  }

  async function create(payload: LibraryCreate): Promise<LibraryRead> {
    const { data } = await client.post<LibraryRead>('/api/libraries', payload)
    await _fetch()
    return data
  }

  async function update(id: number, patch: LibraryUpdate): Promise<LibraryRead> {
    const { data } = await client.patch<LibraryRead>(`/api/libraries/${id}`, patch)
    await _fetch()
    return data
  }

  async function remove(id: number): Promise<void> {
    await client.delete(`/api/libraries/${id}`)
    await _fetch()
  }

  function reset(): void {
    status.value = 'idle'
    error.value = null
  }

  return { items, status, error, byId, totalSeries, load, create, update, remove, reset }
})
