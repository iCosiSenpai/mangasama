<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Search as SearchIcon } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { apiError } from '@/api/client'
import { useLibrariesStore } from '@/stores/libraries'
import { useSearchStore } from '@/stores/search'
import { useSeriesStore } from '@/stores/series'
import ErrorPanel from '@/components/ErrorPanel.vue'

const libraries = useLibrariesStore()
const search = useSearchStore()
const series = useSeriesStore()

const ui = ref({ query: '', libraryId: 0 })

const selectedLibrary = computed(() =>
  libraries.items.find((l) => l.id === ui.value.libraryId) ?? libraries.items[0] ?? null,
)

onMounted(async () => {
  await libraries.load()
  if (libraries.items.length) ui.value.libraryId = libraries.items[0].id
})

async function run(): Promise<void> {
  if (!ui.value.query.trim() || !selectedLibrary.value) return
  await search.run({
    libraryId: selectedLibrary.value.id,
    query: ui.value.query.trim(),
  })
}

async function add(provider: string, externalId: string, title: string): Promise<void> {
  if (!selectedLibrary.value) return
  try {
    await series.addFromCandidate({
      libraryId: selectedLibrary.value.id,
      provider,
      externalId,
    })
    toast.success(`Aggiunta: ${title}`)
  } catch (e) {
    toast.error(apiError(e) || 'Aggiunta serie fallita')
  }
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

    <form class="mb-6 flex flex-wrap gap-2" @submit.prevent="run">
      <select
        v-if="libraries.items.length > 1"
        v-model.number="ui.libraryId"
        aria-label="Libreria di destinazione"
        class="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
      >
        <option v-for="lib in libraries.items" :key="lib.id" :value="lib.id">
          {{ lib.name }}
        </option>
      </select>
      <div class="relative min-w-[12rem] flex-1">
        <SearchIcon
          class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400"
          aria-hidden="true"
        />
        <input
          v-model="ui.query"
          type="text"
          aria-label="Termine di ricerca"
          placeholder="es. Berserk, Naruto, Solo Leveling..."
          class="w-full rounded-md border border-slate-200 bg-white py-2 pl-10 pr-3 text-sm dark:border-slate-700 dark:bg-slate-800"
        />
      </div>
      <button
        type="submit"
        class="btn-primary"
        :disabled="search.status === 'loading' || !ui.query.trim() || !selectedLibrary"
      >
        Cerca
      </button>
    </form>

    <div v-if="search.status === 'loading'" class="text-sm text-slate-500" aria-live="polite">
      Ricerca in corso…
    </div>

    <ErrorPanel
      v-else-if="search.status === 'error'"
      :message="search.error"
      @retry="run"
    />

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
          v-if="selectedLibrary"
          type="button"
          class="btn-primary"
          :disabled="series.adding"
          @click="add(c.provider, c.external_id, c.title)"
        >
          Aggiungi a {{ selectedLibrary.name }}
        </button>
      </li>
    </ul>
  </div>
</template>
