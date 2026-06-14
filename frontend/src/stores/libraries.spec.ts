import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/client', () => ({
  client: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  apiError: (e: unknown) => String(e),
}))

import { client } from '@/api/client'
import { useLibrariesStore } from '@/stores/libraries'

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

const payload = {
  name: 'X',
  type: 'manga' as const,
  root_path: '/x',
  folder_strategy: 'series_volume_chapter' as const,
  providers: ['mangadex'],
  italian_priority: true,
  follow_interval_hours: 24,
  jpg_quality: 85,
}

describe('libraries store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('load() is idempotent (one GET for two calls)', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: [LIB] } as never)
    const s = useLibrariesStore()
    await s.load()
    await s.load()
    expect(client.get).toHaveBeenCalledTimes(1)
    expect(s.items).toHaveLength(1)
  })

  it('create() POSTs then re-fetches', async () => {
    vi.mocked(client.post).mockResolvedValue({ data: LIB } as never)
    vi.mocked(client.get).mockResolvedValue({ data: [LIB] } as never)
    const s = useLibrariesStore()
    const created = await s.create(payload)
    expect(client.post).toHaveBeenCalledWith('/api/libraries', payload)
    expect(client.get).toHaveBeenCalledWith('/api/libraries')
    expect(created.id).toBe(1)
    expect(s.items).toHaveLength(1)
  })

  it('remove() DELETEs then re-fetches', async () => {
    vi.mocked(client.delete).mockResolvedValue({ data: {} } as never)
    vi.mocked(client.get).mockResolvedValue({ data: [] } as never)
    const s = useLibrariesStore()
    await s.remove(1)
    expect(client.delete).toHaveBeenCalledWith('/api/libraries/1')
    expect(client.get).toHaveBeenCalledWith('/api/libraries')
    expect(s.items).toHaveLength(0)
  })
})
