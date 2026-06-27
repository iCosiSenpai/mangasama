<script setup lang="ts">
withDefaults(defineProps<{ count?: number }>(), { count: 1 })
</script>

<template>
  <div
    v-for="i in count"
    :key="i"
    class="card p-4"
    aria-hidden="true"
  >
    <div class="flex items-start justify-between gap-2">
      <div class="skeleton h-5 w-2/3 rounded" />
      <div class="skeleton h-5 w-12 rounded-full" />
    </div>
    <div class="skeleton mt-2 h-3 w-1/2 rounded" />
    <div class="mt-4 grid grid-cols-2 gap-2">
      <div class="skeleton h-8 rounded" />
      <div class="skeleton h-8 rounded" />
    </div>
    <div class="mt-3 flex gap-1.5">
      <div class="skeleton h-5 w-14 rounded-full" />
      <div class="skeleton h-5 w-14 rounded-full" />
    </div>
  </div>
</template>
