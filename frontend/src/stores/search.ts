import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { client } from '@/api/client'
import { apiError } from '@/api/client'
import type { SearchCandidate, SearchResponse } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

/**
 * Multi-source search state. The store keeps the last query + library so the
 * UI can re-render without re-issuing the request. `run()` is idempotent
 * for the same (library, query) tuple.
 */
export const useSearchStore = defineStore('search', () => {
  const query: Ref<string> = ref('')
  const libraryId: Ref<number | null> = ref(null)
  const providersUsed: Ref<string[]> = ref([])
  const candidates: Ref<SearchCandidate[]> = ref([])
  const status: Ref<Status> = ref('idle')
  const error: Ref<string | null> = ref(null)

  const hasResults = computed(() => candidates.value.length > 0)

  async function run(opts: {
    libraryId: number
    query: string
    providers?: string[] | null
    languages?: string[]
    limitPerProvider?: number
  }): Promise<void> {
    if (!opts.query.trim()) {
      reset()
      return
    }
    query.value = opts.query
    libraryId.value = opts.libraryId
    status.value = 'loading'
    error.value = null
    try {
      const { data } = await client.post<SearchResponse>('/api/search', {
        library_id: opts.libraryId,
        query: opts.query,
        providers: opts.providers ?? null,
        languages: opts.languages ?? ['it', 'en'],
        limit_per_provider: opts.limitPerProvider ?? 5,
      })
      providersUsed.value = data.providers_used
      candidates.value = data.candidates
      status.value = 'ready'
    } catch (e) {
      error.value = apiError(e)
      status.value = 'error'
      candidates.value = []
    }
  }

  function reset(): void {
    query.value = ''
    candidates.value = []
    providersUsed.value = []
    error.value = null
    status.value = 'idle'
  }

  return {
    query,
    libraryId,
    providersUsed,
    candidates,
    status,
    error,
    hasResults,
    run,
    reset,
  }
})
