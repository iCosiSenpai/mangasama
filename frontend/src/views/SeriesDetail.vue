<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, Heart, RefreshCw } from 'lucide-vue-next'
import { useSeriesDetailStore } from '@/stores/seriesDetail'
import ChapterList from '@/components/ChapterList.vue'

const route = useRoute()
const router = useRouter()
const store = useSeriesDetailStore()

const backfillCount = ref(10)
const coverError = ref(false)

const seriesId = computed<number | null>(() => {
  const raw = route.params.id
  const parsed = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(parsed) ? parsed : null
})

const authorsByRole = computed<{ role: string; names: string }[]>(() => {
  const map = new Map<string, string[]>()
  for (const a of store.current?.authors ?? []) {
    if (!map.has(a.role)) map.set(a.role, [])
    map.get(a.role)!.push(a.name)
  }
  return [...map.entries()].map(([role, names]) => ({ role, names: names.join(', ') }))
})

async function loadAll(id: number): Promise<void> {
  await store.load(id)
  await store.loadChapters(id)
}

onMounted(() => {
  if (seriesId.value != null) void loadAll(seriesId.value)
})

watch(seriesId, (id) => {
  store.reset()
  if (id != null) void loadAll(id)
})

async function onFollow(): Promise<void> {
  if (!store.current) return
  try {
    await store.toggleFollow(store.current.id, !store.current.followed)
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('follow toggle failed', e)
  }
}

async function onBackfill(): Promise<void> {
  if (seriesId.value == null) return
  try {
    await store.backfill(seriesId.value, backfillCount.value)
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('backfill failed', e)
  }
}
</script>

<template>
  <div>
    <div class="mb-4">
      <button type="button" class="btn" @click="router.back()">
        <ArrowLeft class="size-4" />
        Indietro
      </button>
    </div>

    <div v-if="store.status === 'loading'" class="text-sm text-slate-500">Caricamento…</div>
    <div
      v-else-if="store.status === 'error'"
      class="card p-4 text-rose-600 dark:text-rose-400"
    >
      {{ store.error }}
    </div>
    <div v-else-if="!store.current" class="card p-8 text-center text-slate-500">
      Serie non trovata.
    </div>

    <template v-else>
      <header class="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h1 class="text-2xl font-semibold">{{ store.current.title }}</h1>
            <span v-if="store.current.status" class="chip uppercase">
              {{ store.current.status }}
            </span>
          </div>
          <p class="mt-1 text-xs text-slate-500">
            <span v-if="store.current.year">{{ store.current.year }} · </span>
            <span v-if="store.current.language">{{ store.current.language }} · </span>
            {{ store.current.volume_count }} volumi · {{ store.chapters.length }} capitoli
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn"
            :class="store.current.followed ? 'border-rose-300 text-rose-600 dark:border-rose-700 dark:text-rose-300' : ''"
            :aria-pressed="store.current.followed"
            @click="onFollow"
          >
            <Heart :class="['size-4', store.current.followed ? 'fill-rose-500 stroke-rose-500' : '']" />
            {{ store.current.followed ? 'Seguito' : 'Segui' }}
          </button>
          <button
            type="button"
            class="btn"
            :disabled="store.refreshing"
            @click="store.refreshMetadata(store.current.id)"
          >
            <RefreshCw class="size-4" :class="{ 'animate-spin': store.refreshing }" />
            Metadati
          </button>
          <div class="flex items-center gap-1">
            <input
              v-model.number="backfillCount"
              type="number"
              min="1"
              max="500"
              class="w-16 rounded-md border border-slate-200 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800"
            />
            <button
              type="button"
              class="btn-primary"
              :disabled="store.backfilling"
              @click="onBackfill"
            >
              <Download class="size-4" />
              Backfill
            </button>
          </div>
        </div>
      </header>

      <div class="mb-6 grid gap-4 lg:grid-cols-3">
        <div class="card p-4 lg:col-span-2">
          <h2 class="mb-2 text-sm font-semibold text-slate-500">Trama</h2>
          <p class="whitespace-pre-line text-sm">
            {{ store.current.summary || 'Nessuna descrizione.' }}
          </p>
        </div>
        <div class="card space-y-3 p-4 text-sm">
          <img
            v-if="store.current.cover_path && !coverError"
            :src="`/api/covers/series/${store.current.id}`"
            :alt="store.current.title"
            loading="lazy"
            class="mb-1 max-h-64 w-full rounded-md object-contain"
            @error="coverError = true"
          />
          <div v-if="authorsByRole.length">
            <h3 class="text-xs font-semibold uppercase text-slate-500">Autori</h3>
            <p v-for="a in authorsByRole" :key="a.role">
              <span class="capitalize text-slate-500">{{ a.role }}:</span> {{ a.names }}
            </p>
          </div>
          <div v-if="store.current.genres.length">
            <h3 class="text-xs font-semibold uppercase text-slate-500">Generi</h3>
            <div class="mt-1 flex flex-wrap gap-1">
              <span v-for="g in store.current.genres" :key="g" class="chip">{{ g }}</span>
            </div>
          </div>
          <div v-if="store.current.tags.length">
            <h3 class="text-xs font-semibold uppercase text-slate-500">Tag</h3>
            <div class="mt-1 flex flex-wrap gap-1">
              <span v-for="t in store.current.tags" :key="t" class="chip">{{ t }}</span>
            </div>
          </div>
          <div v-if="store.current.external_ids.length">
            <h3 class="text-xs font-semibold uppercase text-slate-500">Sorgenti</h3>
            <div class="mt-1 flex flex-wrap gap-2">
              <a
                v-for="e in store.current.external_ids"
                :key="`${e.provider}-${e.external_id}`"
                :href="e.url ?? undefined"
                target="_blank"
                rel="noopener"
                class="chip hover:text-brand-600"
              >
                {{ e.provider }}
              </a>
            </div>
          </div>
        </div>
      </div>

      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-lg font-semibold">Capitoli</h2>
        <button type="button" class="btn" @click="store.loadChapters(store.current.id)">
          <RefreshCw class="size-4" />
          Aggiorna
        </button>
      </div>
      <ChapterList
        :chapters="store.chapters"
        :loading="store.chaptersStatus === 'loading'"
      />
    </template>
  </div>
</template>
