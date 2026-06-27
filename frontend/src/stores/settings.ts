import { ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { apiError, client } from '@/api/client'
import type {
  AdminSettings,
  AdminSettingsPatch,
  EffectiveSettings,
  HealthSnapshot,
  SettingsPatch,
} from '@/types/api'

type Status = 'idle' | 'loading' | 'ready' | 'error'

/** Effective config + provider health for SettingsView. */
export const useSettingsStore = defineStore('settings', () => {
  const effective: Ref<EffectiveSettings | null> = ref(null)
  const health: Ref<HealthSnapshot | null> = ref(null)
  const adminSettings: Ref<AdminSettings | null> = ref(null)
  const adminStatus: Ref<Status> = ref('idle')
  const adminError: Ref<string | null> = ref(null)
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

  async function runBackup(): Promise<{ created: string; total_backups: number }> {
    const { data } = await client.post<{ created: string; size_bytes: number; total_backups: number }>(
      '/api/settings/backup',
    )
    return data
  }

  async function patchSettings(body: SettingsPatch): Promise<void> {
    const { data } = await client.patch<EffectiveSettings>('/api/settings', body)
    effective.value = data
  }

  async function runHealthCheck(): Promise<void> {
    await client.post('/api/settings/providers/health/check')
    await load()
  }

  async function resetProvider(source: string): Promise<void> {
    await client.post(`/api/settings/providers/${source}/reset`)
    await load()
  }

  async function loadAdminSettings(): Promise<void> {
    adminStatus.value = 'loading'
    adminError.value = null
    try {
      const { data } = await client.get<AdminSettings>('/api/admin/settings')
      adminSettings.value = data
      adminStatus.value = 'ready'
    } catch (e) {
      adminError.value = apiError(e)
      adminStatus.value = 'error'
    }
  }

  async function patchAdminSettings(body: AdminSettingsPatch): Promise<void> {
    const { data } = await client.put<AdminSettings>('/api/admin/settings', body)
    adminSettings.value = data
  }

  return {
    effective,
    health,
    adminSettings,
    adminStatus,
    adminError,
    status,
    error,
    load,
    runBackup,
    patchSettings,
    runHealthCheck,
    resetProvider,
    loadAdminSettings,
    patchAdminSettings,
  }
})
