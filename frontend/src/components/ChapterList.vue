<script setup lang="ts">
import { ref } from 'vue'
import { Download, RotateCcw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { downloadAuthenticated } from '@/api/authFetch'
import type { ChapterListItem } from '@/types/api'

defineProps<{
  chapters: ChapterListItem[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'redownload', chapterId: number): void
}>()

const downloading = ref<number | null>(null)

function fmtSize(bytes: number | null): string {
  if (!bytes) return '—'
  const mb = bytes / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString()
}

async function onDownload(ch: ChapterListItem): Promise<void> {
  downloading.value = ch.id
  try {
    const name = `chapter-${ch.number}${ch.language ? `-${ch.language}` : ''}.cbz`
    await downloadAuthenticated(`/api/chapters/${ch.id}/file`, name)
  } catch {
    toast.error('Download fallito')
  } finally {
    downloading.value = null
  }
}
</script>

<template>
  <div class="card overflow-hidden">
    <div v-if="loading && !chapters.length" class="p-4 text-sm text-slate-500">
      Caricamento capitoli…
    </div>
    <div v-else-if="!chapters.length" class="p-8 text-center text-sm text-slate-500">
      Nessun capitolo ancora. Usa "Backfill" per scaricarne.
    </div>
    <table v-else class="w-full text-sm">
      <thead
        class="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500 dark:border-slate-800 dark:bg-slate-800/50"
      >
        <tr>
          <th scope="col" class="px-3 py-2 font-medium">Cap.</th>
          <th scope="col" class="px-3 py-2 font-medium">Titolo</th>
          <th scope="col" class="px-3 py-2 font-medium">Lingua</th>
          <th scope="col" class="px-3 py-2 font-medium">Pagine</th>
          <th scope="col" class="px-3 py-2 font-medium">CBZ</th>
          <th scope="col" class="px-3 py-2 font-medium">Azioni</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="ch in chapters"
          :key="ch.id"
          class="border-b border-slate-100 last:border-0 dark:border-slate-800"
        >
          <td class="px-3 py-2 font-mono text-xs">{{ ch.number }}</td>
          <td class="px-3 py-2">
            <span class="truncate">{{ ch.title || '—' }}</span>
          </td>
          <td class="px-3 py-2"><span class="chip uppercase">{{ ch.language }}</span></td>
          <td class="px-3 py-2 text-slate-500">{{ ch.pages_count ?? '—' }}</td>
          <td class="px-3 py-2">
            <button
              v-if="ch.downloaded_at"
              type="button"
              class="inline-flex items-center gap-1 text-brand-600 hover:underline disabled:opacity-50"
              :disabled="downloading === ch.id"
              :title="`${fmtSize(ch.cbz_size)} · ${fmtDate(ch.downloaded_at)}`"
              @click="onDownload(ch)"
            >
              <Download class="size-3.5" /> {{ fmtSize(ch.cbz_size) }}
            </button>
            <span v-else class="text-slate-400">—</span>
          </td>
          <td class="px-3 py-2">
            <button
              v-if="ch.downloaded_at"
              type="button"
              class="btn"
              title="Riscarica capitolo"
              aria-label="Riscarica capitolo"
              @click="emit('redownload', ch.id)"
            >
              <RotateCcw class="size-3.5" aria-hidden="true" />
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
