<script setup lang="ts">
import { AlertTriangle, RotateCcw } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    message?: string | null
    retryable?: boolean
  }>(),
  { message: null, retryable: true },
)

const emit = defineEmits<{ (e: 'retry'): void }>()
</script>

<template>
  <div
    class="card flex flex-col items-start gap-2 p-4 text-sm text-rose-600 dark:text-rose-400"
    role="alert"
  >
    <div class="flex items-center gap-2">
      <AlertTriangle class="size-4 shrink-0" aria-hidden="true" />
      <span>{{ message || 'Si è verificato un errore.' }}</span>
    </div>
    <button
      v-if="retryable"
      type="button"
      class="btn"
      @click="emit('retry')"
    >
      <RotateCcw class="size-4" aria-hidden="true" />
      Riprova
    </button>
  </div>
</template>
