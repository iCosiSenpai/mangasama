import { ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { client } from '@/api/client'
import type { SetupPayload, SetupStatus } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error' | 'submitting'

/**
 * First-run setup state. The backend decides whether the wizard must be shown
 * via `/api/setup/status`.
 */
export const useSetupStore = defineStore('setup', () => {
  const status: Ref<Status> = ref('idle')
  const error: Ref<string | null> = ref(null)
  const setupRequired: Ref<boolean | null> = ref(null)

  async function checkStatus(): Promise<boolean> {
    status.value = 'loading'
    error.value = null
    try {
      const { data } = await client.get<SetupStatus>('/api/setup/status')
      setupRequired.value = data.setup_required
      status.value = 'ready'
      return data.setup_required
    } catch (e) {
      error.value = 'Impossibile verificare lo stato di setup'
      status.value = 'error'
      return false
    }
  }

  async function complete(payload: SetupPayload): Promise<void> {
    status.value = 'submitting'
    error.value = null
    try {
      await client.post('/api/setup', payload)
      setupRequired.value = false
      status.value = 'ready'
    } catch (e) {
      const err = e as { detail?: string }
      error.value = err.detail ?? 'Setup fallito'
      status.value = 'error'
      throw e
    }
  }

  return {
    status,
    error,
    setupRequired,
    checkStatus,
    complete,
  }
})
