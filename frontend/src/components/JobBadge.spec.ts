import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import JobBadge from '@/components/JobBadge.vue'

describe('JobBadge', () => {
  it('renders running with progress', () => {
    const w = mount(JobBadge, { props: { status: 'running', progress: 42 } })
    expect(w.text()).toContain('running')
    expect(w.text()).toContain('42%')
  })

  it('renders done', () => {
    const w = mount(JobBadge, { props: { status: 'done' } })
    expect(w.text()).toContain('done')
  })

  it('renders error', () => {
    const w = mount(JobBadge, { props: { status: 'error' } })
    expect(w.text()).toContain('error')
  })

  it('falls back to the raw status for unknown values', () => {
    const w = mount(JobBadge, { props: { status: 'pending' } })
    expect(w.text()).toContain('pending')
  })
})
