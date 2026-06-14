<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import { useLibrariesStore } from '@/stores/libraries'
import { useSeriesStore } from '@/stores/series'
import SeriesCard from '@/components/SeriesCard.vue'
import SearchDialog from '@/components/SearchDialog.vue'
import LibraryForm from '@/components/LibraryForm.vue'

const route = useRoute()
const router = useRouter()
const libraries = useLibrariesStore()
const series = useSeriesStore()

const dialogOpen = ref(false)
const editOpen = ref(false)

async function deleteLibrary(): Promise<void> {
  if (libraryId.value == null) return
  if (!window.confirm('Eliminare questa libreria? (i file su disco restano)')) return
  try {
    await libraries.remove(libraryId.value)
    await router.push('/')
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('delete library failed', e)
  }
}

const libraryId = computed<number | null>(() => {
  const raw = route.params.id
  const parsed = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(parsed) ? parsed : null
})

const library = computed(() => {
  if (libraryId.value == null) return null
  return libraries.byId[libraryId.value] ?? null
})

const followedCount = computed(() => series.followedCount)

onMounted(async () => {
  await libraries.load()
  if (libraryId.value != null) {
    await series.load(libraryId.value)
  }
})

watch(libraryId, async (id) => {
  if (id != null) {
    await series.load(id)
  } else {
    series.reset()
  }
})

function onAdded(payload: { seriesId: number; title: string }): void {
  dialogOpen.value = false
  // eslint-disable-next-line no-console
  console.info(`added series id=${payload.seriesId} "${payload.title}"`)
}
</script>

<template>
  <div>
    <div class="mb-4">
      <button
        type="button"
        class="btn"
        @click="router.push('/')"
      >
        <ArrowLeft class="size-4" />
        Librerie
      </button>
    </div>

    <div v-if="!library" class="card p-8 text-center text-slate-500">
      Libreria non trovata.
    </div>

    <template v-else>
      <header class="mb-6 flex items-start justify-between gap-4">
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-2xl font-semibold">{{ library.name }}</h1>
            <span class="chip uppercase">{{ library.type }}</span>
          </div>
          <p class="font-mono text-xs text-slate-500">{{ library.root_path }}</p>
          <p class="mt-2 text-sm text-slate-500 dark:text-slate-400">
            {{ series.items.length }} serie ·
            {{ followedCount }} seguite
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="btn" @click="editOpen = true">
            <Pencil class="size-4" />
            Modifica
          </button>
          <button
            type="button"
            class="btn border-rose-300 text-rose-600 dark:border-rose-700 dark:text-rose-300"
            @click="deleteLibrary"
          >
            <Trash2 class="size-4" />
            Elimina
          </button>
          <button type="button" class="btn-primary" @click="dialogOpen = true">
            <Plus class="size-4" />
            Aggiungi serie
          </button>
        </div>
      </header>

      <div
        v-if="series.status === 'loading'"
        class="text-sm text-slate-500"
      >
        Caricamento…
      </div>
      <div
        v-else-if="series.status === 'error'"
        class="card p-4 text-rose-600 dark:text-rose-400"
      >
        {{ series.error }}
      </div>
      <div
        v-else-if="!series.items.length"
        class="card p-8 text-center text-slate-500"
      >
        Nessuna serie. Clicca "Aggiungi serie" per iniziare.
      </div>
      <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SeriesCard
          v-for="s in series.items"
          :key="s.id"
          :series="s"
        />
      </div>

      <SearchDialog
        :open="dialogOpen"
        :default-library-id="libraryId"
        @close="dialogOpen = false"
        @added="onAdded"
      />

      <LibraryForm
        :open="editOpen"
        :library="library"
        @close="editOpen = false"
        @saved="editOpen = false"
      />
    </template>
  </div>
</template>
