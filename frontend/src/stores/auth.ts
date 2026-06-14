import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { client } from '@/api/client'

const STORAGE_KEY = 'mangasama.auth'

/**
 * Single-admin auth. The backend gate (HTTP Basic) is optional; this store
 * holds the base64 `admin:<password>` credential, persists it, and attaches
 * it to every axios request. A 401 from the API clears it (see client.ts).
 */
export const useAuthStore = defineStore('auth', () => {
  const credential: Ref<string | null> = ref(localStorage.getItem(STORAGE_KEY))
  const isAuthed = computed(() => credential.value !== null)

  function _apply(cred: string | null): void {
    if (cred) client.defaults.headers.common.Authorization = `Basic ${cred}`
    else delete client.defaults.headers.common.Authorization
  }

  /** Re-attach a persisted credential to the axios client on app boot. */
  function hydrate(): void {
    _apply(credential.value)
  }

  function login(password: string): void {
    const cred = btoa(`admin:${password}`)
    credential.value = cred
    localStorage.setItem(STORAGE_KEY, cred)
    _apply(cred)
  }

  function logout(): void {
    credential.value = null
    localStorage.removeItem(STORAGE_KEY)
    _apply(null)
  }

  return { isAuthed, hydrate, login, logout }
})
