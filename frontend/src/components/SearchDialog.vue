<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Loader2, Plus, Search, X } from 'lucide-vue-next'
import { useLibrariesStore } from '@/stores/libraries'
import { useSearchStore } from '@/stores/search'
import { useSeriesStore } from '@/stores/series'

const props = defineProps<{
  open: boolean
  // Default library to pre-select when the dialog opens.
  defaultLibraryId?: number | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'added', payload: { seriesId: number; title: string }): void
}>()

const libraries = useLibrariesStore()
const search = useSearchStore()
const series = useSeriesStore()

const ui = reactive({
  libraryId: props.defaultLibraryId ?? null,
  query: '',
  providers: null as string[] | null,
})

const queryInput = ref<HTMLInputElement | null>(null)

// Reset state when the dialog opens.
watch(
  () => props.open,
  (open) => {
    if (!open) return
    search.reset()
    ui.query = ''
    ui.providers = null
    if (
      !ui.libraryId ||
      !libraries.items.find((l) => l.id === ui.libraryId)
    ) {
      ui.libraryId = libraries.items[0]?.id ?? null
    }
    // Focus the search input on the next tick.
    setTimeout(() => queryInput.value?.focus(), 0)
  },
  { immediate: true },
)

const availableProviders = computed(() => {
  const lib = libraries.items.find((l) => l.id === ui.libraryId)
  return lib?.providers ?? []
})

const canSearch = computed(
  () => !!ui.libraryId && ui.query.trim().length > 0,
)

async function runSearch(): Promise<void> {
  if (!canSearch.value || !ui.libraryId) return
  await search.run({
    libraryId: ui.libraryId,
    query: ui.query.trim(),
    providers: ui.providers,
  })
}

async function addCandidate(
  provider: string,
  externalId: string,
  title: string,
): Promise<void> {
  if (!ui.libraryId) return
  try {
    const created = (await series.addFromCandidate({
      libraryId: ui.libraryId,
      provider,
      externalId,
      runMetadataRefresh: true,
    })) as unknown as { id: number; title: string }
    emit('added', {
      seriesId: created.id ?? 0,
      title: created.title ?? title,
    })
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('add series failed', e)
  }
}

function onBackdropClick(): void {
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-label="Aggiungi serie"
      @click.self="onBackdropClick"
    >
      <div
        class="ml-auto flex h-full w-full max-w-xl flex-col bg-white shadow-2xl dark:bg-slate-900"
      >
        <header
          class="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800"
        >
          <h2 class="text-lg font-semibold">Cerca e aggiungi serie</h2>
          <button
            type="button"
            class="btn"
            aria-label="Chiudi"
            @click="emit('close')"
          >
            <X class="size-4" />
          </button>
        </header>

        <div class="space-y-3 border-b border-slate-200 p-5 dark:border-slate-800">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">
              Libreria di destinazione
            </label>
            <select
              v-model.number="ui.libraryId"
              class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800"
            >
              <option
                v-for="lib in libraries.items"
                :key="lib.id"
                :value="lib.id"
              >
                {{ lib.name }}
              </option>
            </select>
          </div>

          <form class="flex gap-2" @submit.prevent="runSearch">
            <div class="relative flex-1">
              <Search
                class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400"
              />
              <input
                ref="queryInput"
                v-model="ui.query"
                type="text"
                placeholder="es. One Piece"
                class="w-full rounded-md border border-slate-200 bg-white py-1.5 pl-8 pr-3 text-sm dark:border-slate-700 dark:bg-slate-800"
                :disabled="!ui.libraryId"
              />
            </div>
            <button
              type="submit"
              class="btn-primary"
              :disabled="!canSearch || search.status === 'loading'"
            >
              <Loader2
                v-if="search.status === 'loading'"
                class="size-4 animate-spin"
              />
              <Search v-else class="size-4" />
              Cerca
            </button>
          </form>

          <div v-if="availableProviders.length > 1" class="flex flex-wrap gap-1.5">
            <button
              v-for="p in availableProviders"
              :key="p"
              type="button"
              class="chip"
              :class="{
                'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-200':
                  ui.providers?.includes(p),
              }"
              @click="
                () => {
                  if (!ui.providers) {
                    ui.providers = [p]
                  } else if (ui.providers.includes(p)) {
                    ui.providers = ui.providers.filter((x) => x !== p)
                    if (ui.providers.length === 0) ui.providers = null
                  } else {
                    ui.providers = [...ui.providers, p]
                  }
                }
              "
            >
              {{ p }}
            </button>
            <button
              v-if="ui.providers"
              type="button"
              class="chip"
              @click="ui.providers = null"
            >
              tutti
            </button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto p-5">
          <div
            v-if="search.status === 'idle'"
            class="text-sm text-slate-500"
          >
            Digita una query e premi Cerca.
          </div>
          <div
            v-else-if="search.status === 'error'"
            class="text-sm text-rose-600 dark:text-rose-400"
          >
            {{ search.error }}
          </div>
          <div
            v-else-if="search.status === 'ready' && !search.hasResults"
            class="text-sm text-slate-500"
          >
            Nessun risultato per "{{ search.query }}".
          </div>
          <ul v-else class="space-y-2">
            <li
              v-for="c in search.candidates"
              :key="`${c.provider}-${c.external_id}`"
              class="card flex items-start gap-3 p-3"
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
                  <span v-if="c.year" class="text-xs text-slate-500">
                    {{ c.year }}
                  </span>
                </div>
                <p class="mt-1 truncate font-medium" :title="c.title">
                  {{ c.title }}
                </p>
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
                :disabled="series.adding"
                @click="addCandidate(c.provider, c.external_id, c.title)"
              >
                <Plus class="size-4" />
                Aggiungi
              </button>
            </li>
          </ul>
        </div>

        <footer
          class="border-t border-slate-200 px-5 py-2 text-xs text-slate-500 dark:border-slate-800"
        >
          Provider usati: {{ search.providersUsed.join(', ') || '—' }}
        </footer>
      </div>
    </div>
  </Teleport>
</template>
