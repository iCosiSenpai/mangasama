<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { BookMarked, FolderPlus, Loader2, Trash2, User } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import { useSetupStore } from '@/stores/setup'
import { apiError } from '@/api/client'
import type { LibraryCreate, LibraryFolderStrategy, LibraryType, SetupPayload } from '@/types/api'

const router = useRouter()
const setupStore = useSetupStore()
const auth = useAuthStore()
const settings = useSettingsStore()

const TYPES: LibraryType[] = ['manga', 'manhua', 'manhwa']
const STRATEGIES: LibraryFolderStrategy[] = [
  'series_volume_chapter',
  'series_volume',
  'chapter_flat',
  'onefile_per_volume',
]
const COVER_STRATEGIES = ['series_first', 'volume_first', 'chapter_first'] as const

const step = ref(1)
const submitting = ref(false)

const account = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})

const libraries = reactive<LibraryCreate[]>([])

function blankLibrary(): LibraryCreate {
  return {
    name: '',
    type: 'manga',
    root_path: '',
    folder_strategy: 'series_volume_chapter',
    cover_strategy: 'series_first',
    providers: [...(settings.effective?.known_scrapers ?? [])],
    italian_priority: true,
    follow_interval_hours: 24,
    jpg_quality: 85,
  }
}

onMounted(async () => {
  await settings.load()
  if (libraries.length === 0) {
    libraries.push(blankLibrary())
  }
})

function addLibrary(): void {
  libraries.push(blankLibrary())
}

function removeLibrary(index: number): void {
  libraries.splice(index, 1)
}

function toggleProvider(lib: LibraryCreate, p: string): void {
  lib.providers = lib.providers.includes(p)
    ? lib.providers.filter((x) => x !== p)
    : [...lib.providers, p]
}

const knownScrapers = computed(() => settings.effective?.known_scrapers ?? [])

const accountValid = computed(() => {
  return (
    account.username.length >= 3 &&
    account.password.length >= 8 &&
    account.password === account.confirmPassword
  )
})

const librariesValid = computed(() => {
  return libraries.length > 0 && libraries.every(
    (l) => l.name.trim().length > 0 && l.root_path.trim().length > 0 && l.providers.length > 0,
  )
})

const canSubmit = computed(() => accountValid.value && librariesValid.value)

async function submit(): Promise<void> {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  try {
    const payload: SetupPayload = {
      admin: {
        username: account.username.trim(),
        password: account.password,
      },
      libraries: libraries.map((l) => ({
        ...l,
        name: l.name.trim(),
        root_path: l.root_path.trim(),
        providers: [...l.providers],
      })),
    }
    await setupStore.complete(payload)
    await auth.login(account.username.trim(), account.password)
    toast.success('Setup completato')
    void router.push('/')
  } catch (e) {
    toast.error(apiError(e) ?? 'Setup fallito')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-950">
    <form class="card w-full max-w-2xl p-6" @submit.prevent="submit">
      <div class="mb-6 flex items-center gap-2 text-xl font-semibold">
        <BookMarked class="size-6 text-brand-600" />
        MangaSama — Configurazione iniziale
      </div>

      <!-- Step indicator -->
      <div class="mb-6 flex items-center gap-2 text-sm">
        <span
          class="size-8 rounded-full flex items-center justify-center font-semibold"
          :class="step >= 1 ? 'bg-brand-600 text-white' : 'bg-slate-200 dark:bg-slate-800'"
        >
          1
        </span>
        <span class="text-slate-400">/</span>
        <span
          class="size-8 rounded-full flex items-center justify-center font-semibold"
          :class="step >= 2 ? 'bg-brand-600 text-white' : 'bg-slate-200 dark:bg-slate-800'"
        >
          2
        </span>
      </div>

      <!-- Account -->
      <div v-if="step === 1" class="space-y-4">
        <div class="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-500">
          <User class="size-4" />
          Account admin
        </div>
        <p class="text-xs text-slate-500">
          Crea le credenziali che userai per accedere a MangaSama e al catalogo OPDS.
        </p>

        <div>
          <label for="setup-username" class="mb-1 block text-xs font-medium text-slate-500">Username</label>
          <input
            id="setup-username"
            v-model="account.username"
            type="text"
            autocomplete="username"
            placeholder="es. admin"
            class="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
          />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label for="setup-password" class="mb-1 block text-xs font-medium text-slate-500">Password</label>
            <input
              id="setup-password"
              v-model="account.password"
              type="password"
              autocomplete="new-password"
              placeholder="Min. 8 caratteri"
              class="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
            />
          </div>
          <div>
            <label for="setup-password-confirm" class="mb-1 block text-xs font-medium text-slate-500">Conferma password</label>
            <input
              id="setup-password-confirm"
              v-model="account.confirmPassword"
              type="password"
              autocomplete="new-password"
              placeholder="Ripeti password"
              class="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
            />
          </div>
        </div>

        <p v-if="account.password && account.password !== account.confirmPassword" class="text-xs text-rose-600">
          Le password non coincidono.
        </p>

        <div class="flex justify-end">
          <button
            type="button"
            class="btn-primary"
            :disabled="!accountValid"
            @click="step = 2"
          >
            Avanti
          </button>
        </div>
      </div>

      <!-- Libraries -->
      <div v-else class="space-y-4">
        <div class="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-500">
          <FolderPlus class="size-4" />
          Cartelle manga
        </div>
        <p class="text-xs text-slate-500">
          Ogni libreria deve puntare a una cartella montata nel compose. Aggiungine quante ne hai bisogno.
        </p>

        <div v-for="(lib, index) in libraries" :key="index" class="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-xs font-semibold text-slate-500">Libreria {{ index + 1 }}</span>
            <button
              v-if="libraries.length > 1"
              type="button"
              class="btn text-xs"
              @click="removeLibrary(index)"
            >
              <Trash2 class="size-4" />
            </button>
          </div>

          <div class="space-y-3">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label :for="`lib-name-${index}`" class="mb-1 block text-xs font-medium text-slate-500">Nome</label>
                <input
                  :id="`lib-name-${index}`"
                  v-model="lib.name"
                  type="text"
                  placeholder="es. Manga IT"
                  class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800"
                />
              </div>
              <div>
                <label :for="`lib-type-${index}`" class="mb-1 block text-xs font-medium text-slate-500">Tipo</label>
                <select
                  :id="`lib-type-${index}`"
                  v-model="lib.type"
                  class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800"
                >
                  <option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
                </select>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label :for="`lib-folder-${index}`" class="mb-1 block text-xs font-medium text-slate-500">Folder strategy</label>
                <select
                  :id="`lib-folder-${index}`"
                  v-model="lib.folder_strategy"
                  class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800"
                >
                  <option v-for="s in STRATEGIES" :key="s" :value="s">{{ s }}</option>
                </select>
              </div>
              <div>
                <label :for="`lib-cover-${index}`" class="mb-1 block text-xs font-medium text-slate-500">Cover strategy</label>
                <select
                  :id="`lib-cover-${index}`"
                  v-model="lib.cover_strategy"
                  class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800"
                >
                  <option v-for="s in COVER_STRATEGIES" :key="s" :value="s">{{ s }}</option>
                </select>
              </div>
            </div>

            <div>
              <label :for="`lib-root-${index}`" class="mb-1 block text-xs font-medium text-slate-500">Root path (montato nel compose)</label>
              <input
                :id="`lib-root-${index}`"
                v-model="lib.root_path"
                type="text"
                placeholder="/libraries/manga"
                class="w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 font-mono text-xs dark:border-slate-700 dark:bg-slate-800"
              />
            </div>

            <div>
              <span class="mb-1 block text-xs font-medium text-slate-500">Provider</span>
              <div v-if="knownScrapers.length" class="flex flex-wrap gap-1.5">
                <button
                  v-for="p in knownScrapers"
                  :key="p"
                  type="button"
                  class="chip"
                  :class="{
                    'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-200':
                      lib.providers.includes(p),
                  }"
                  @click="toggleProvider(lib, p)"
                >
                  {{ p }}
                </button>
              </div>
              <p v-else class="text-xs text-slate-500">Nessuno scraper disponibile.</p>
            </div>
          </div>
        </div>

        <button type="button" class="btn w-full" @click="addLibrary">
          <FolderPlus class="size-4" />
          Aggiungi altra cartella
        </button>

        <div class="flex justify-between">
          <button type="button" class="btn" @click="step = 1">Indietro</button>
          <button
            type="submit"
            class="btn-primary"
            :disabled="!canSubmit || submitting"
          >
            <Loader2 v-if="submitting" class="size-4 animate-spin" />
            Completa setup
          </button>
        </div>
      </div>
    </form>
  </div>
</template>
