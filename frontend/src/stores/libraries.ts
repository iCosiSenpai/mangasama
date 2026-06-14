import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { client } from '@/api/client'
import type { LibraryRead } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

/**
 * Single store for the libraries list. `load()` is idempotent and safe to
 * call from multiple `onMounted` hooks (sidebar, library list view).
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

  async function load(): Promise<void> {
    // Skip the network roundtrip if we already have a fresh copy.
    if (status.value === 'loading' || status.value === 'ready') return
    status.value = 'loading'
    error.value = null
    try {
      const { data } = await client.get<LibraryRead[]>('/api/libraries')
      items.value = data
      status.value = 'ready'
    } catch (e) {
      const payload = e as { detail?: string }
      error.value = payload.detail ?? 'Errore sconosciuto'
      status.value = 'error'
    }
  }

  function reset(): void {
    status.value = 'idle'
    error.value = null
  }

  return { items, status, error, byId, totalSeries, load, reset }
})
