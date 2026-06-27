<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    message?: string
  }>(),
  { title: '', message: '' },
)
</script>

<template>
  <div class="card p-8 text-center text-slate-500">
    <div v-if="$slots.icon" class="mb-2 flex justify-center text-slate-400">
      <slot name="icon" />
    </div>
    <p v-if="title" class="font-medium text-slate-600 dark:text-slate-300">{{ title }}</p>
    <p v-if="message" class="mt-1 text-sm">{{ message }}</p>
    <slot />
    <div v-if="$slots.action" class="mt-4 flex justify-center">
      <slot name="action" />
    </div>
  </div>
</template>
