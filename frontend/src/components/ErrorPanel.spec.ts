import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ErrorPanel from './ErrorPanel.vue'

describe('ErrorPanel', () => {
  it('renders the provided message', () => {
    const wrapper = mount(ErrorPanel, { props: { message: 'Boom happened' } })
    expect(wrapper.text()).toContain('Boom happened')
    expect(wrapper.attributes('role')).toBe('alert')
  })

  it('falls back to a default message when none is given', () => {
    const wrapper = mount(ErrorPanel, { props: { message: null } })
    expect(wrapper.text()).toContain('Si è verificato un errore.')
  })

  it('emits retry when the retry button is clicked', async () => {
    const wrapper = mount(ErrorPanel, { props: { message: 'x' } })
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('hides the retry button when not retryable', () => {
    const wrapper = mount(ErrorPanel, { props: { message: 'x', retryable: false } })
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
