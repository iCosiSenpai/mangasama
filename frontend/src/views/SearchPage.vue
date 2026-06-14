<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Search as SearchIcon } from 'lucide-vue-next'
import { useLibrariesStore } from '@/stores/libraries'
import { useSearchStore } from '@/stores/search'
import { useSeriesStore } from '@/stores/series'

const libraries = useLibrariesStore()
const search = useSearchStore()
const series = useSeriesStore()

const ui = ref({ query: '' })

onMounted(async () => {
  await libraries.load()
})

async function run(): Promise<void> {
  if (!ui.value.query.trim()) return
  if (!libraries.items.length) return
  // Use the first library as a default target. Users can refine in the dialog.
  await search.run({
    libraryId: libraries.items[0].id,
    query: ui.value.query.trim(),
  })
}
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-semibold">Cerca</h1>
      <p class="text-sm text-slate-500 dark:text-slate-400">
        Cerca serie su tutti i provider configurati. Usa "Aggiungi" per metterle in una libreria.
      </p>
    </div>

    <form class="mb-6 flex gap-2" @submit.prevent="run">
      <div class="relative flex-1">
        <SearchIcon
          class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400"
        />
        <input
          v-model="ui.query"
          type="text"
          placeholder="es. Berserk, Naruto, Solo Leveling..."
          class="w-full rounded-md border border-slate-200 bg-white py-2 pl-10 pr-3 text-sm dark:border-slate-700 dark:bg-slate-800"
        />
      </div>
      <button
        type="submit"
        class="btn-primary"
        :disabled="search.status === 'loading' || !ui.query.trim()"
      >
        Cerca
      </button>
    </form>

    <div v-if="search.status === 'loading'" class="text-sm text-slate-500">
      Ricerca in corso…
    </div>

    <div
      v-else-if="search.status === 'error'"
      class="card p-4 text-rose-600 dark:text-rose-400"
    >
      {{ search.error }}
    </div>

    <div
      v-else-if="search.status === 'ready' && !search.hasResults"
      class="text-sm text-slate-500"
    >
      Nessun risultato per "{{ search.query }}".
    </div>

    <ul v-else-if="search.hasResults" class="space-y-2">
      <li
        v-for="c in search.candidates"
        :key="`${c.provider}-${c.external_id}`"
        class="card flex items-start gap-3 p-4"
      >
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="chip">{{ c.provider }}</span>
            <span
              v-if="c.is_italian_available"
              class="chip bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200"
            >
              IT
            </span>
            <span v-if="c.year" class="text-xs text-slate-500">{{ c.year }}</span>
            <span v-if="c.type" class="text-xs text-slate-500 uppercase">
              {{ c.type }}
            </span>
          </div>
          <p class="mt-1 font-medium">{{ c.title }}</p>
          <p
            v-if="c.alt_titles?.length"
            class="truncate text-xs text-slate-500"
            :title="c.alt_titles.join(', ')"
          >
            {{ c.alt_titles.join(', ') }}
          </p>
        </div>
        <button
          type="button"
          class="btn-primary"
          :disabled="series.adding || !libraries.items.length"
          @click="
            series.addFromCandidate({
              libraryId: libraries.items[0].id,
              provider: c.provider,
              externalId: c.external_id,
            })
          "
        >
          Aggiungi a {{ libraries.items[0]?.name }}
        </button>
      </li>
    </ul>
  </div>
</template>
