<script setup lang="ts">
import { Download } from 'lucide-vue-next'
import type { ChapterListItem } from '@/types/api'

defineProps<{
  chapters: ChapterListItem[]
  loading?: boolean
}>()

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
          <th class="px-3 py-2 font-medium">Cap.</th>
          <th class="px-3 py-2 font-medium">Titolo</th>
          <th class="px-3 py-2 font-medium">Lingua</th>
          <th class="px-3 py-2 font-medium">Pagine</th>
          <th class="px-3 py-2 font-medium">CBZ</th>
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
            <a
              v-if="ch.downloaded_at"
              :href="`/api/chapters/${ch.id}/file`"
              class="inline-flex items-center gap-1 text-brand-600 hover:underline"
              :title="`${fmtSize(ch.cbz_size)} · ${fmtDate(ch.downloaded_at)}`"
            >
              <Download class="size-3.5" /> {{ fmtSize(ch.cbz_size) }}
            </a>
            <span v-else class="text-slate-400">—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
