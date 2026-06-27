<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Activity, Database, RefreshCw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useSettingsStore } from '@/stores/settings'

const store = useSettingsStore()

const backingUp = ref(false)
const backupMsg = ref<string | null>(null)
const logLevel = ref('INFO')
const healthRunning = ref(false)

async function doBackup(): Promise<void> {
  backingUp.value = true
  backupMsg.value = null
  try {
    const res = await store.runBackup()
    backupMsg.value = `Backup creato: ${res.created} (${res.total_backups} totali)`
    toast.success('Backup creato')
  } catch {
    backupMsg.value = 'Backup fallito'
    toast.error('Backup fallito')
  } finally {
    backingUp.value = false
  }
}

async function saveLogLevel(): Promise<void> {
  try {
    await store.patchSettings({ log_level: logLevel.value })
    toast.success('Log level aggiornato')
  } catch {
    toast.error('Salvataggio fallito')
  }
}

async function runHealthCheck(): Promise<void> {
  healthRunning.value = true
  try {
    await store.runHealthCheck()
    toast.success('Health check completato')
  } catch {
    toast.error('Health check fallito')
  } finally {
    healthRunning.value = false
  }
}

async function resetProvider(source: string): Promise<void> {
  try {
    await store.resetProvider(source)
    toast.success(`Provider ${source} resettato`)
  } catch {
    toast.error('Reset fallito')
  }
}

const defaults = computed<[string, unknown][]>(() =>
  Object.entries(store.effective?.library_defaults ?? {}),
)

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

onMounted(async () => {
  await store.load()
  if (store.effective) logLevel.value = store.effective.log_level
})
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Settings</h1>
      <button type="button" class="btn" @click="store.load()">
        <RefreshCw class="size-4" />
        Aggiorna
      </button>
    </div>

    <div v-if="store.status === 'loading'" class="text-sm text-slate-500">Caricamento…</div>
    <div
      v-else-if="store.status === 'error'"
      class="card p-4 text-rose-600 dark:text-rose-400"
    >
      {{ store.error }}
    </div>

    <div v-else-if="store.effective" class="grid gap-4 lg:grid-cols-2">
      <div class="card p-4">
        <h2 class="mb-3 text-sm font-semibold text-slate-500">Applicazione</h2>
        <dl class="space-y-1 text-sm">
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">App</dt>
            <dd>{{ store.effective.app_name }} {{ store.effective.version }}</dd>
          </div>
          <div class="flex items-center justify-between gap-4">
            <dt class="text-slate-500">Log level</dt>
            <dd class="flex items-center gap-2">
              <select
                v-model="logLevel"
                class="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-800"
              >
                <option>DEBUG</option>
                <option>INFO</option>
                <option>WARNING</option>
                <option>ERROR</option>
              </select>
              <button type="button" class="btn" @click="saveLogLevel">Salva</button>
            </dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">Data dir</dt>
            <dd class="truncate font-mono text-xs" :title="store.effective.data_dir">
              {{ store.effective.data_dir }}
            </dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-slate-500">Config dir</dt>
            <dd class="truncate font-mono text-xs" :title="store.effective.config_dir">
              {{ store.effective.config_dir }}
            </dd>
          </div>
        </dl>

        <h3 class="mt-4 text-xs font-semibold uppercase text-slate-500">Scraper</h3>
        <div class="mt-1 flex flex-wrap gap-1">
          <span
            v-for="s in store.effective.known_scrapers"
            :key="s"
            class="chip"
            :class="store.effective.enabled_scrapers.includes(s)
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200'
              : ''"
          >
            {{ s }}
          </span>
        </div>

        <h3 v-if="defaults.length" class="mt-4 text-xs font-semibold uppercase text-slate-500">
          Default libreria
        </h3>
        <dl v-if="defaults.length" class="mt-1 space-y-1 text-sm">
          <div v-for="[k, v] in defaults" :key="k" class="flex justify-between gap-4">
            <dt class="text-slate-500">{{ k }}</dt>
            <dd class="text-right">{{ Array.isArray(v) ? v.join(', ') : String(v) }}</dd>
          </div>
        </dl>

        <h3 class="mt-4 text-xs font-semibold uppercase text-slate-500">Backup</h3>
        <div class="mt-1 flex items-center gap-3">
          <button type="button" class="btn" :disabled="backingUp" @click="doBackup">
            <Database class="size-4" :class="{ 'animate-pulse': backingUp }" />
            Backup ora
          </button>
          <span v-if="backupMsg" class="text-xs text-slate-500">{{ backupMsg }}</span>
        </div>
      </div>

      <div class="card p-4">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-500">Provider health</h2>
          <button type="button" class="btn" :disabled="healthRunning" @click="runHealthCheck">
            <Activity class="size-4" :class="{ 'animate-pulse': healthRunning }" />
            Ping ora
          </button>
        </div>
        <table v-if="store.health && store.health.providers.length" class="w-full text-sm">
          <thead class="text-left text-xs uppercase text-slate-500">
            <tr>
              <th class="py-1 font-medium">Provider</th>
              <th class="py-1 font-medium">Stato</th>
              <th class="py-1 font-medium">Fail</th>
              <th class="py-1 font-medium">Ultimo OK</th>
              <th class="py-1 font-medium" />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in store.health.providers"
              :key="p.provider"
              class="border-t border-slate-100 dark:border-slate-800"
            >
              <td class="py-1.5">{{ p.provider }}</td>
              <td class="py-1.5">
                <span class="inline-flex items-center gap-1.5">
                  <span
                    class="size-2 rounded-full"
                    :class="p.healthy ? 'bg-emerald-500' : 'bg-rose-500'"
                  />
                  {{ p.healthy ? 'sano' : 'down' }}
                </span>
              </td>
              <td class="py-1.5 text-slate-500">{{ p.fail_count }}</td>
              <td class="py-1.5 text-xs text-slate-500">{{ fmtDate(p.last_ok) }}</td>
              <td class="py-1.5 text-right">
                <button
                  v-if="!p.healthy"
                  type="button"
                  class="btn text-xs"
                  @click="resetProvider(p.provider)"
                >
                  Reset
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="text-sm text-slate-500">Nessun provider monitorato.</p>
      </div>
    </div>
  </div>
</template>
