import { ref } from 'vue'

const STORAGE_KEY = 'mangasama.theme'
type Theme = 'light' | 'dark'

const isDark = ref(true)

function apply(theme: Theme): void {
  isDark.value = theme === 'dark'
  document.documentElement.classList.toggle('dark', isDark.value)
}

/**
 * Read the persisted theme (falling back to the OS preference, then the
 * `index.html` default of dark) and apply it. Call once on app boot.
 */
export function initTheme(): void {
  const stored = localStorage.getItem(STORAGE_KEY) as Theme | null
  if (stored === 'light' || stored === 'dark') {
    apply(stored)
    return
  }
  const prefersDark =
    typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
      : true
  apply(prefersDark ? 'dark' : 'light')
}

/** Reactive theme state + a persistent toggle for the UI. */
export function useTheme() {
  function toggle(): void {
    const next: Theme = isDark.value ? 'light' : 'dark'
    apply(next)
    localStorage.setItem(STORAGE_KEY, next)
  }
  return { isDark, toggle }
}
