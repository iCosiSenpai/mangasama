import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/client', () => ({
  client: { get: vi.fn(), post: vi.fn() },
  apiError: (e: unknown) => String(e),
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { client } from '@/api/client'
import { toast } from 'vue-sonner'
import SearchPage from '@/views/SearchPage.vue'
import { useSearchStore } from '@/stores/search'

const LIB = {
  id: 1,
  name: 'X',
  type: 'manga',
  root_path: '/x',
  folder_strategy: 'series_volume_chapter',
  cover_strategy: 'series_first',
  providers: ['mangadex'],
  italian_priority: true,
  follow_interval_hours: 24,
  jpg_quality: 85,
  series_count: 0,
  created_at: '',
  updated_at: '',
  deleted: false,
}

const CANDIDATE = {
  provider: 'mangadex',
  external_id: 'abc',
  url: null,
  title: 'Naruto',
  alt_titles: [],
  year: 1999,
  cover_url: null,
  language: 'it',
  type: 'manga',
  score: 1,
  is_italian_available: true,
}

const STUBS = { RouterLink: true }

describe('SearchPage add flow', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.mocked(client.get).mockResolvedValue({ data: [LIB] } as never)
  })

  async function mountWithCandidate() {
    const w = mount(SearchPage, { global: { stubs: STUBS } })
    await flushPromises() // onMounted → libraries.load
    const search = useSearchStore()
    search.candidates = [CANDIDATE]
    search.status = 'ready'
    await flushPromises()
    return w
  }

  it('toasts success when adding a candidate succeeds', async () => {
    vi.mocked(client.post).mockResolvedValue({ data: { id: 9, title: 'Naruto' } } as never)
    const w = await mountWithCandidate()
    await w.get('li button').trigger('click')
    await flushPromises()
    expect(client.post).toHaveBeenCalledWith('/api/series', expect.objectContaining({
      library_id: 1,
      provider: 'mangadex',
      external_id: 'abc',
    }))
    expect(toast.success).toHaveBeenCalledTimes(1)
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('toasts error instead of an unhandled rejection when adding fails', async () => {
    vi.mocked(client.post).mockRejectedValue(new Error('boom') as never)
    const w = await mountWithCandidate()
    await w.get('li button').trigger('click')
    await flushPromises()
    expect(toast.error).toHaveBeenCalledTimes(1)
    expect(toast.success).not.toHaveBeenCalled()
  })
})
