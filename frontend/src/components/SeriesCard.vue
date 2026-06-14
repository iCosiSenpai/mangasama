<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Calendar, Hash, Languages } from 'lucide-vue-next'
import type { SeriesListItem } from '@/types/api'
import FollowButton from './FollowButton.vue'

const props = defineProps<{ series: SeriesListItem }>()

const imgError = ref(false)
</script>

<template>
  <div class="card flex flex-col p-4 transition-colors hover:border-brand-500">
    <RouterLink
      v-if="props.series.cover_path && !imgError"
      :to="`/series/${series.id}`"
      class="mb-3 block overflow-hidden rounded-md"
    >
      <img
        :src="`/api/covers/series/${series.id}`"
        :alt="series.title"
        loading="lazy"
        class="h-44 w-full object-cover"
        @error="imgError = true"
      />
    </RouterLink>

    <div class="flex items-start justify-between gap-2">
      <RouterLink
        :to="`/series/${series.id}`"
        class="flex-1 truncate font-semibold hover:text-brand-600"
      >
        {{ series.title }}
      </RouterLink>
      <span
        v-if="series.status"
        class="chip uppercase"
        :title="`status: ${series.status}`"
      >
        {{ series.status }}
      </span>
    </div>

    <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
      <span v-if="series.year" class="inline-flex items-center gap-1">
        <Calendar class="size-3" /> {{ series.year }}
      </span>
      <span v-if="series.language" class="inline-flex items-center gap-1">
        <Languages class="size-3" /> {{ series.language }}
      </span>
      <span
        v-for="eid in series.external_ids"
        :key="`${eid.provider}-${eid.external_id}`"
        class="inline-flex items-center gap-1"
      >
        <Hash class="size-3" /> {{ eid.provider }}
      </span>
    </div>

    <div class="mt-auto pt-3">
      <FollowButton :series-id="series.id" :followed="series.followed" />
    </div>
  </div>
</template>
