<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Loader2, X } from 'lucide-vue-next'
import { useLibrariesStore } from '@/stores/libraries'
import { useSettingsStore } from '@/stores/settings'
import type { LibraryFolderStrategy, LibraryRead, LibraryType } from '@/types/api'

const props = defineProps<{
  open: boolean
  library?: LibraryRead | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved', id: number): void
}>()

const libraries = useLibrariesStore()
const settings = useSettingsStore()

const TYPES: LibraryType[] = ['manga', 'manhua', 'manhwa']
const STRATEGIES: LibraryFolderStrategy[] = [
  'series_volume_chapter',
  'series_volume',
  'chapter_flat',
  'onefile_per_volume',
]

const saving = ref(false)
const error = ref<string | null>(null)

const isEdit = computed(() => !!props.library)
const title = computed(() => (isEdit.value ? 'Modifica libreria' : 'Nuova libreria'))

function blank() {
  return {
    name: '',
    type: 'manga' as LibraryType,
    root_path: '',
    folder_strategy: 'series_volume_chapter' as LibraryFolderStrategy,
    providers: [] as string[],
    italian_priority: true,
    follow_interval_hours: 24,
    jpg_quality: 85,
  }
}

const form = reactive(blank())

const knownScrapers = computed<string[]>(() => settings.effective?.known_scrapers ?? [])

function hydrate(): void {
  error.value = null
  if (props.library) {
    Object.assign(form, {
      name: props.library.name,
      type: props.library.type,
      root_path: props.library.root_path,
      folder_strategy: props.library.folder_strategy,
      providers: [...props.library.providers],
      italian_priority: props.library.italian_priority,
      follow_interval_hours: props.library.follow_interval_hours,
      jpg_quality: props.library.jpg_quality,
    })
  } else {
    Object.assign(form, blank())
    // Pre-select all known scrapers for a fresh library.
    form.providers = [...knownScrapers.value]
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    void settings.load().then(() => {
      if (!props.library && form.providers.length === 0) {
        form.providers = [...knownScrapers.value]
      }
    })
    hydrate()
  },
  { immediate: true },
)

function toggleProvider(p: string): void {
  form.providers = form.providers.includes(p)
    ? form.providers.filter((x) => x !== p)
    : [...form.providers, p]
}

const canSave = computed(() => form.name.trim().length > 0 && form.root_path.trim().length > 0)

async function submit(): Promise<void> {
  if (!canSave.value || saving.value) return
  saving.value = true
  error.value = null
  try {
    const payload = {
      name: form.name.trim(),
      type: form.type,
      root_path: form.root_path.trim(),
      folder_strategy: form.folder_strategy,
      providers: [...form.providers],
      italian_priority: form.italian_priority,
      follow_interval_hours: form.follow_interval_hours,
      jpg_quality: form.jpg_quality,
    }
    const saved = props.library
      ? await libraries.update(props.library.id, payload)
      : await libraries.create(payload)
    emit('saved', saved.id)
  } catch (e) {
    const payload = e as { detail?: string }
    error.value = payload.detail ?? 'Errore nel salvataggio'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex bg-black/40"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      @click.self="emit('close')"
    >
      <form
        class="ml-auto flex h-full w-full max-w-md flex-col bg-white shadow-2xl dark:bg-slate-900"
        @submit.prevent="submit"
      >
        <header
          class="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800"
        >
          <h2 class="text-lg font-semibold">{{ title }}</h2>
          <button type="button" class="btn" aria-label="Chiudi" @click="emit('close')">
            <X class="size-4" />
          </button>
        </header>

        <div class="flex-1 space-y-4 overflow-y-auto p-5 text-sm">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">Nome</label>
            <input
              v-model="form.name"
              type="text"
              placeholder="es. Manga IT"
              class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-800"
            />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs font-medium text-slate-500">Tipo</label>
              <select
                v-model="form.type"
                class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-800"
              >
                <option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-slate-500">Folder strategy</label>
              <select
                v-model="form.folder_strategy"
                class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-800"
              >
                <option v-for="s in STRATEGIES" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">Root path</label>
            <input
              v-model="form.root_path"
              type="text"
              placeholder="/data/manga_it"
              class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 font-mono text-xs dark:border-slate-700 dark:bg-slate-800"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">Provider</label>
            <div v-if="knownScrapers.length" class="flex flex-wrap gap-1.5">
              <button
                v-for="p in knownScrapers"
                :key="p"
                type="button"
                class="chip"
                :class="{
                  'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-200':
                    form.providers.includes(p),
                }"
                @click="toggleProvider(p)"
              >
                {{ p }}
              </button>
            </div>
            <p v-else class="text-xs text-slate-500">Nessuno scraper disponibile.</p>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs font-medium text-slate-500">Follow ogni (ore)</label>
              <input
                v-model.number="form.follow_interval_hours"
                type="number"
                min="1"
                max="8760"
                class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-800"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-slate-500">Qualità JPG</label>
              <input
                v-model.number="form.jpg_quality"
                type="number"
                min="1"
                max="100"
                class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-800"
              />
            </div>
          </div>

          <label class="flex items-center gap-2">
            <input v-model="form.italian_priority" type="checkbox" class="size-4" />
            <span>Priorità italiano</span>
          </label>

          <p v-if="error" class="text-rose-600 dark:text-rose-400">{{ error }}</p>
        </div>

        <footer
          class="flex justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800"
        >
          <button type="button" class="btn" @click="emit('close')">Annulla</button>
          <button type="submit" class="btn-primary" :disabled="!canSave || saving">
            <Loader2 v-if="saving" class="size-4 animate-spin" />
            {{ isEdit ? 'Salva' : 'Crea' }}
          </button>
        </footer>
      </form>
    </div>
  </Teleport>
</template>
