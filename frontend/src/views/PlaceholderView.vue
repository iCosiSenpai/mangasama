<script setup lang="ts">
import { computed } from 'vue'
import {
  BookOpen,
  Briefcase,
  Library,
  Search,
  Settings,
} from 'lucide-vue-next'

const props = defineProps<{
  title: string
  step: number
}>()

const icon = computed(() => {
  switch (props.title) {
    case 'Library detail':
      return Library
    case 'Series detail':
      return BookOpen
    case 'Search':
      return Search
    case 'Jobs':
      return Briefcase
    case 'Settings':
      return Settings
    default:
      return BookOpen
  }
})
</script>

<template>
  <div class="card mx-auto max-w-lg p-8 text-center">
    <component :is="icon" class="mx-auto mb-3 size-10 text-slate-400" />
    <h2 class="text-lg font-semibold">{{ title }}</h2>
    <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
      Coming in step {{ step }}.
    </p>
    <RouterLink to="/" class="btn mt-4">Torna alle librerie</RouterLink>
  </div>
</template>
