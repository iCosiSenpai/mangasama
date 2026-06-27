import { beforeEach, describe, expect, it, vi } from 'vitest'
import { initTheme, useTheme } from './useTheme'

const STORAGE_KEY = 'mangasama.theme'

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('applies the persisted theme on init', () => {
    localStorage.setItem(STORAGE_KEY, 'light')
    initTheme()
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    localStorage.setItem(STORAGE_KEY, 'dark')
    initTheme()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('falls back to OS preference when nothing is stored', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({ matches: true }) as unknown as typeof window.matchMedia,
    )
    initTheme()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    vi.unstubAllGlobals()
  })

  it('toggle flips and persists the theme', () => {
    localStorage.setItem(STORAGE_KEY, 'dark')
    initTheme()
    const { isDark, toggle } = useTheme()
    expect(isDark.value).toBe(true)

    toggle()
    expect(isDark.value).toBe(false)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    toggle()
    expect(localStorage.getItem(STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
