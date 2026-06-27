import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { client, apiError } from '@/api/client'
import type { FollowSummary } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

export const useFollowStore = defineStore('follow', () => {
  const items: Ref<FollowSummary[]> = ref([])
  const status: Ref<Status> = ref('idle')
  const error: Ref<string | null> = ref(null)
  const checking: Ref<number | null> = ref(null)

  const count = computed(() => items.value.length)

  async function load(): Promise<void> {
    status.value = 'loading'
    error.value = null
    try {
      const { data } = await client.get<FollowSummary[]>('/api/follow')
      items.value = data
      status.value = 'ready'
    } catch (e) {
      error.value = apiError(e)
      status.value = 'error'
    }
  }

  async function checkSeries(seriesId: number): Promise<void> {
    checking.value = seriesId
    try {
      await client.post(`/api/follow/${seriesId}/check`)
      await load()
    } finally {
      checking.value = null
    }
  }

  return { items, status, error, checking, count, load, checkSeries }
})
