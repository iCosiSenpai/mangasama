<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, Clock, Loader2, XCircle } from 'lucide-vue-next'

const props = defineProps<{
  status: string
  progress?: number
}>()

const meta = computed(() => {
  switch (props.status) {
    case 'running':
      return {
        icon: Loader2,
        spin: true,
        cls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200',
        label: 'running',
      }
    case 'done':
      return {
        icon: CheckCircle2,
        spin: false,
        cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200',
        label: 'done',
      }
    case 'error':
      return {
        icon: XCircle,
        spin: false,
        cls: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200',
        label: 'error',
      }
    default:
      return {
        icon: Clock,
        spin: false,
        cls: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
        label: props.status || 'pending',
      }
  }
})
</script>

<template>
  <span
    class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
    :class="meta.cls"
  >
    <component :is="meta.icon" class="size-3" :class="{ 'animate-spin': meta.spin }" />
    {{ meta.label }}
    <template v-if="status === 'running' && typeof progress === 'number'">
      · {{ progress }}%
    </template>
  </span>
</template>
