import { ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { apiError, client } from '@/api/client'
import type { EffectiveSettings, HealthSnapshot } from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

/** Read-only view of effective config + provider health for SettingsView. */
export const useSettingsStore = defineStore('settings', () => {
  const effective: Ref<EffectiveSettings | null> = ref(null)
  const health: Ref<HealthSnapshot | null> = ref(null)
  const status: Ref<Status> = ref('idle')
  const error: Ref<string | null> = ref(null)

  async function load(): Promise<void> {
    status.value = 'loading'
    error.value = null
    try {
      const [s, h] = await Promise.all([
        client.get<EffectiveSettings>('/api/settings'),
        client.get<HealthSnapshot>('/api/settings/providers/health'),
      ])
      effective.value = s.data
      health.value = h.data
      status.value = 'ready'
    } catch (e) {
      error.value = apiError(e)
      status.value = 'error'
    }
  }

  return { effective, health, status, error, load }
})
