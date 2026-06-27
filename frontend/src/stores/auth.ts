import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { client } from '@/api/client'

const STORAGE_KEY = 'mangasama.auth'

/**
 * Single-admin auth. The backend gate (HTTP Basic) is active once setup is
 * completed. This store holds the base64 `<username>:<password>` credential,
 * persists it, and attaches it to every axios request. A 401 from the API
 * clears it (see client.ts).
 */
export const useAuthStore = defineStore('auth', () => {
  const credential: Ref<string | null> = ref(localStorage.getItem(STORAGE_KEY))
  const username: Ref<string | null> = ref(localStorage.getItem('mangasama.auth.username'))
  const isAuthed = computed(() => credential.value !== null)

  function _apply(cred: string | null): void {
    if (cred) client.defaults.headers.common.Authorization = `Basic ${cred}`
    else delete client.defaults.headers.common.Authorization
  }

  /** Re-attach a persisted credential to the axios client on app boot. */
  function hydrate(): void {
    _apply(credential.value)
  }

  async function login(usernameValue: string, password: string): Promise<void> {
    const cred = btoa(`${usernameValue}:${password}`)
    const prev = client.defaults.headers.common.Authorization
    client.defaults.headers.common.Authorization = `Basic ${cred}`
    try {
      await client.get('/api/settings')
    } catch (e) {
      delete client.defaults.headers.common.Authorization
      if (prev) client.defaults.headers.common.Authorization = prev
      throw e
    }
    credential.value = cred
    username.value = usernameValue
    localStorage.setItem(STORAGE_KEY, cred)
    localStorage.setItem('mangasama.auth.username', usernameValue)
    _apply(cred)
  }

  function logout(): void {
    credential.value = null
    username.value = null
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem('mangasama.auth.username')
    _apply(null)
  }

  return { isAuthed, username, hydrate, login, logout }
})
