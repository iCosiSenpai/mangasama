<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { useJobsStore } from '@/stores/jobs'
import JobBadge from '@/components/JobBadge.vue'

const jobs = useJobsStore()

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString()
}

onMounted(() => {
  void jobs.load()
  jobs.connect()
})

onUnmounted(() => {
  jobs.disconnect()
})
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold">Jobs</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400">
          {{ jobs.items.length }} job · {{ jobs.runningCount }} attivi
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span class="flex items-center gap-1.5 text-xs text-slate-500">
          <span
            class="size-2 rounded-full"
            :class="jobs.streaming ? 'bg-emerald-500' : 'bg-slate-400'"
          />
          {{ jobs.streaming ? 'live' : 'offline' }}
        </span>
        <button type="button" class="btn" @click="jobs.load()">
          <RefreshCw class="size-4" />
          Aggiorna
        </button>
      </div>
    </div>

    <div v-if="jobs.status === 'loading' && !jobs.items.length" class="text-sm text-slate-500">
      Caricamento…
    </div>

    <div
      v-else-if="jobs.status === 'error'"
      class="card p-4 text-rose-600 dark:text-rose-400"
    >
      <p>Errore: {{ jobs.error }}</p>
      <button type="button" class="btn ml-2" @click="jobs.load()">Riprova</button>
    </div>

    <div v-else-if="!jobs.items.length" class="card p-8 text-center text-slate-500">
      Nessun job. Avvia un backfill o un follow per vederli comparire qui in tempo reale.
    </div>

    <div v-else class="card overflow-hidden">
      <table class="w-full text-sm">
        <thead
          class="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500 dark:border-slate-800 dark:bg-slate-800/50"
        >
          <tr>
            <th class="px-3 py-2 font-medium">#</th>
            <th class="px-3 py-2 font-medium">Tipo</th>
            <th class="px-3 py-2 font-medium">Provider</th>
            <th class="px-3 py-2 font-medium">Stato</th>
            <th class="px-3 py-2 font-medium">Inizio</th>
            <th class="px-3 py-2 font-medium">Fine</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="job in jobs.items"
            :key="job.id"
            class="border-b border-slate-100 last:border-0 dark:border-slate-800"
          >
            <td class="px-3 py-2 font-mono text-xs text-slate-500">{{ job.id }}</td>
            <td class="px-3 py-2">{{ job.job_type }}</td>
            <td class="px-3 py-2">
              <span v-if="job.provider" class="chip">{{ job.provider }}</span>
              <span v-else class="text-slate-400">—</span>
            </td>
            <td class="px-3 py-2">
              <JobBadge :status="job.status" :progress="job.progress" />
              <p
                v-if="job.error"
                class="mt-1 max-w-md truncate text-xs text-rose-500"
                :title="job.error"
              >
                {{ job.error }}
              </p>
            </td>
            <td class="px-3 py-2 text-xs text-slate-500">{{ fmtTime(job.started_at) }}</td>
            <td class="px-3 py-2 text-xs text-slate-500">{{ fmtTime(job.finished_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
