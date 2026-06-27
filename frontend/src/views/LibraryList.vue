<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Plus } from 'lucide-vue-next'
import { client } from '@/api/client'
import { useLibrariesStore } from '@/stores/libraries'
import type { LibraryStats } from '@/types/api'
import LibraryForm from '@/components/LibraryForm.vue'

const store = useLibrariesStore()
const ui = reactive({ creating: false })
const statsById = ref<Record<number, LibraryStats>>({})

function fmtBytes(n: number): string {
  if (!n) return '0 B'
  const mb = n / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`
}

async function loadStats(): Promise<void> {
  const entries = await Promise.all(
    store.items.map(async (lib) => {
      try {
        const { data } = await client.get<LibraryStats>(`/api/libraries/${lib.id}/stats`)
        return [lib.id, data] as const
      } catch {
        return null
      }
    }),
  )
  const next: Record<number, LibraryStats> = {}
  for (const e of entries) {
    if (e) next[e[0]] = e[1]
  }
  statsById.value = next
}

onMounted(async () => {
  await store.load(true)
  await loadStats()
})
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold">Librerie</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400">
          {{ store.items.length }} librerie · {{ store.totalSeries }} serie totali
        </p>
      </div>
      <button type="button" class="btn-primary" @click="ui.creating = true">
        <Plus class="size-4" />
        Crea libreria
      </button>
    </div>

    <div v-if="store.status === 'loading'" class="text-sm text-slate-500">
      Caricamento…
    </div>

    <div
      v-else-if="store.status === 'error'"
      class="card p-4 text-rose-600 dark:text-rose-400"
    >
      <p>Errore: {{ store.error }}</p>
      <button
        type="button"
        class="btn ml-2"
        @click="store.reset(); void store.load(true)"
      >
        Riprova
      </button>
    </div>

    <div
      v-else-if="!store.items.length"
      class="card p-8 text-center text-slate-500"
    >
      Nessuna libreria. Clicca "Crea libreria" per iniziare.
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <RouterLink
        v-for="lib in store.items"
        :key="lib.id"
        :to="`/library/${lib.id}`"
        class="card block p-4 transition-colors hover:border-brand-500"
      >
        <div class="flex items-start justify-between gap-2">
          <h3 class="truncate font-semibold">{{ lib.name }}</h3>
          <span class="chip uppercase">{{ lib.type }}</span>
        </div>
        <p
          class="mt-1 truncate font-mono text-xs text-slate-500"
          :title="lib.root_path"
        >
          {{ lib.root_path }}
        </p>

        <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
          <div>
            <div class="text-slate-500 dark:text-slate-400">Serie</div>
            <div class="text-base font-semibold">{{ lib.series_count }}</div>
          </div>
          <div>
            <div class="text-slate-500 dark:text-slate-400">Disk</div>
            <div class="text-base font-semibold">
              {{ statsById[lib.id] ? fmtBytes(statsById[lib.id].total_bytes) : '—' }}
            </div>
          </div>
        </div>

        <div class="mt-3 flex flex-wrap gap-1.5">
          <span v-for="p in lib.providers" :key="p" class="chip">{{ p }}</span>
          <span v-if="lib.italian_priority" class="chip">italian</span>
          <span class="chip">follow {{ lib.follow_interval_hours }}h</span>
        </div>
      </RouterLink>
    </div>

    <LibraryForm
      :open="ui.creating"
      @close="ui.creating = false"
      @saved="ui.creating = false"
    />
  </div>
</template>
