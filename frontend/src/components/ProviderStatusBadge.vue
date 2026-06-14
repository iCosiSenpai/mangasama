<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { client } from '@/api/client'
import type { HealthSnapshot } from '@/types/api'

type Status = 'green' | 'gray' | 'red'

const status = ref<Status>('gray')
const label = ref<string>('Caricamento…')

onMounted(async () => {
  try {
    const { data } = await client.get<HealthSnapshot>(
      '/api/settings/providers/health',
    )
    const total = data.providers.length
    const failing = data.providers.filter((p) => !p.healthy).length
    if (total === 0) {
      status.value = 'gray'
      label.value = 'Nessun provider'
    } else if (failing === 0) {
      status.value = 'green'
      label.value = `${total} provider OK`
    } else if (failing >= Math.ceil(total / 2)) {
      status.value = 'red'
      label.value = `${failing}/${total} non sani`
    } else {
      status.value = 'gray'
      label.value = `${failing}/${total} non sani`
    }
  } catch {
    status.value = 'gray'
    label.value = 'Stato non disponibile'
  }
})

const dotClass = {
  green: 'bg-emerald-500',
  red: 'bg-rose-500',
  gray: 'bg-slate-400',
} as const
</script>

<template>
  <span class="inline-flex items-center gap-1.5" :title="label">
    <span
      :class="['inline-block size-2 rounded-full', dotClass[status]]"
      aria-hidden="true"
    />
    <span class="sr-only">{{ label }}</span>
  </span>
</template>
