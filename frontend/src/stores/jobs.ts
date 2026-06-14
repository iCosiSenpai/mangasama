import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { apiError, client } from '@/api/client'
import type { JobEvent, JobRead } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

const MAX_ITEMS = 200

/**
 * Background-job store. `load()` fetches the recent history from
 * `GET /api/jobs`; `connect()` opens an SSE stream (`/api/jobs/stream`) and
 * merges live state changes into the same list, so the view shows both
 * history and live progress without polling.
 */
export const useJobsStore = defineStore('jobs', () => {
  const items: Ref<JobRead[]> = ref([])
  const status: Ref<Status> = ref('idle')
  const error: Ref<string | null> = ref(null)
  const streaming: Ref<boolean> = ref(false)

  let es: EventSource | null = null

  const runningCount = computed(
    () => items.value.filter((j) => j.status === 'running' || j.status === 'pending').length,
  )

  async function load(): Promise<void> {
    status.value = 'loading'
    error.value = null
    try {
      const { data } = await client.get<JobRead[]>('/api/jobs', { params: { limit: 100 } })
      items.value = data
      status.value = 'ready'
    } catch (e) {
      error.value = apiError(e)
      status.value = 'error'
    }
  }

  function _upsert(ev: JobEvent): void {
    const idx = items.value.findIndex((j) => j.id === ev.id)
    if (idx >= 0) {
      const prev = items.value[idx]
      items.value[idx] = {
        ...prev,
        status: ev.status,
        progress: ev.progress,
        error: ev.error,
        finished_at:
          ev.status === 'done' || ev.status === 'error'
            ? new Date().toISOString()
            : prev.finished_at,
      }
    } else {
      items.value.unshift({
        id: ev.id,
        job_type: ev.job_type,
        provider: ev.provider,
        status: ev.status,
        progress: ev.progress,
        message: null,
        started_at: new Date().toISOString(),
        finished_at: ev.status === 'done' || ev.status === 'error' ? new Date().toISOString() : null,
        error: ev.error,
      })
      if (items.value.length > MAX_ITEMS) items.value.length = MAX_ITEMS
    }
  }

  function connect(): void {
    if (es) return
    es = new EventSource('/api/jobs/stream')
    es.onopen = () => {
      streaming.value = true
    }
    es.onmessage = (msg: MessageEvent<string>) => {
      try {
        _upsert(JSON.parse(msg.data) as JobEvent)
      } catch {
        // Ignore keepalive/comment frames that aren't JSON `data:` lines.
      }
    }
    es.onerror = () => {
      // The browser auto-reconnects; just reflect the transient state.
      streaming.value = false
    }
  }

  function disconnect(): void {
    if (es) {
      es.close()
      es = null
    }
    streaming.value = false
  }

  return { items, status, error, streaming, runningCount, load, connect, disconnect }
})
