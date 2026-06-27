import { ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { apiError, client } from '@/api/client'
import type { ChapterListItem, SeriesRead } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

/**
 * Detail state for a single series: the full record + its chapters, plus
 * the follow / backfill / metadata-refresh actions. Separate from the
 * library-scoped `useSeriesStore` (which is the list).
 */
export const useSeriesDetailStore = defineStore('seriesDetail', () => {
  const current: Ref<SeriesRead | null> = ref(null)
  const chapters: Ref<ChapterListItem[]> = ref([])
  const status: Ref<Status> = ref('idle')
  const chaptersStatus: Ref<Status> = ref('idle')
  const error: Ref<string | null> = ref(null)
  const chaptersError: Ref<string | null> = ref(null)
  const backfilling: Ref<boolean> = ref(false)
  const refreshing: Ref<boolean> = ref(false)

  async function load(id: number): Promise<void> {
    status.value = 'loading'
    error.value = null
    try {
      const { data } = await client.get<SeriesRead>(`/api/series/${id}`)
      current.value = data
      status.value = 'ready'
    } catch (e) {
      error.value = apiError(e)
      status.value = 'error'
    }
  }

  async function loadChapters(id: number): Promise<void> {
    chaptersStatus.value = 'loading'
    chaptersError.value = null
    try {
      const { data } = await client.get<ChapterListItem[]>('/api/chapters', {
        params: { series_id: id, limit: 500 },
      })
      chapters.value = data
      chaptersStatus.value = 'ready'
    } catch (e) {
      chaptersError.value = apiError(e)
      chaptersStatus.value = 'error'
    }
  }

  async function toggleFollow(id: number, followed: boolean): Promise<void> {
    const url = followed ? `/api/series/${id}/follow` : `/api/series/${id}/unfollow`
    await client.post(url)
    if (current.value && current.value.id === id) current.value.followed = followed
  }

  async function backfill(id: number, count: number): Promise<number> {
    backfilling.value = true
    try {
      const { data } = await client.post<{ scheduled: number }>(
        `/api/series/${id}/backfill`,
        null,
        { params: { count, language_priority: ['it', 'en'] } },
      )
      // Give the workers a moment, then refresh the chapter list.
      window.setTimeout(() => void loadChapters(id), 4000)
      return data.scheduled
    } finally {
      backfilling.value = false
    }
  }

  async function refreshMetadata(id: number): Promise<void> {
    refreshing.value = true
    try {
      await client.post(`/api/series/${id}/metadata/refresh`)
      await load(id)
    } finally {
      refreshing.value = false
    }
  }

  async function redownloadChapter(chapterId: number, seriesId: number): Promise<void> {
    await client.post(`/api/chapters/${chapterId}/redownload`)
    window.setTimeout(() => void loadChapters(seriesId), 3000)
  }

  function reset(): void {
    current.value = null
    chapters.value = []
    status.value = 'idle'
    chaptersStatus.value = 'idle'
    error.value = null
    chaptersError.value = null
  }

  return {
    current,
    chapters,
    status,
    chaptersStatus,
    error,
    chaptersError,
    backfilling,
    refreshing,
    load,
    loadChapters,
    toggleFollow,
    backfill,
    refreshMetadata,
    redownloadChapter,
    reset,
  }
})
