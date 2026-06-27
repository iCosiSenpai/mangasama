<script setup lang="ts">
import { onMounted } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useFollowStore } from '@/stores/follow'

const store = useFollowStore()

onMounted(() => {
  void store.load()
})

async function onCheck(seriesId: number): Promise<void> {
  try {
    await store.checkSeries(seriesId)
    toast.success('Controllo avviato')
  } catch {
    toast.error('Controllo fallito')
  }
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString()
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold">Serie seguite</h1>
        <p class="text-sm text-slate-500">{{ store.count }} serie in follow</p>
      </div>
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
    <div v-else-if="!store.items.length" class="card p-8 text-center text-slate-500">
      Nessuna serie seguita.
    </div>
    <div v-else class="card overflow-hidden">
      <table class="w-full text-sm">
        <thead class="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500 dark:border-slate-800 dark:bg-slate-800/50">
          <tr>
            <th class="px-3 py-2 font-medium">Titolo</th>
            <th class="px-3 py-2 font-medium">Ultimo check</th>
            <th class="px-3 py-2 font-medium">Stato</th>
            <th class="px-3 py-2 font-medium">Nuovi cap.</th>
            <th class="px-3 py-2 font-medium" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in store.items"
            :key="item.series_id"
            class="border-b border-slate-100 last:border-0 dark:border-slate-800"
          >
            <td class="px-3 py-2">
              <RouterLink :to="`/series/${item.series_id}`" class="font-medium hover:text-brand-600">
                {{ item.title }}
              </RouterLink>
            </td>
            <td class="px-3 py-2 text-slate-500">{{ fmtDate(item.last_checked_at) }}</td>
            <td class="px-3 py-2">{{ item.last_status || '—' }}</td>
            <td class="px-3 py-2">{{ item.last_new_chapters ?? '—' }}</td>
            <td class="px-3 py-2 text-right">
              <button
                type="button"
                class="btn"
                :disabled="store.checking === item.series_id"
                @click="onCheck(item.series_id)"
              >
                Controlla
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
