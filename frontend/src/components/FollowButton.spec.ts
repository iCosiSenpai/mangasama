import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/client', () => ({
  client: { post: vi.fn(), get: vi.fn() },
  apiError: (e: unknown) => String(e),
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { client } from '@/api/client'
import { toast } from 'vue-sonner'
import FollowButton from '@/components/FollowButton.vue'

describe('FollowButton', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('follows and toasts success', async () => {
    vi.mocked(client.post).mockResolvedValue({ data: {} } as never)
    const w = mount(FollowButton, { props: { seriesId: 1, followed: false } })
    await w.get('button').trigger('click')
    await flushPromises()
    expect(client.post).toHaveBeenCalledWith('/api/series/1/follow')
    expect(toast.success).toHaveBeenCalledTimes(1)
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('unfollows when already followed', async () => {
    vi.mocked(client.post).mockResolvedValue({ data: {} } as never)
    const w = mount(FollowButton, { props: { seriesId: 7, followed: true } })
    await w.get('button').trigger('click')
    await flushPromises()
    expect(client.post).toHaveBeenCalledWith('/api/series/7/unfollow')
  })

  it('toasts error when the request fails', async () => {
    vi.mocked(client.post).mockRejectedValue(new Error('boom') as never)
    const w = mount(FollowButton, { props: { seriesId: 1, followed: false } })
    await w.get('button').trigger('click')
    await flushPromises()
    expect(toast.error).toHaveBeenCalledTimes(1)
  })
})
