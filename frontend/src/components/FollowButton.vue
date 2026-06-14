<script setup lang="ts">
import { Heart } from 'lucide-vue-next'
import { useSeriesStore } from '@/stores/series'

const props = defineProps<{
  seriesId: number
  followed: boolean
}>()

const store = useSeriesStore()

async function toggle(): Promise<void> {
  try {
    await store.setFollowed(props.seriesId, !props.followed)
  } catch (e) {
    // Surface as a console error for now; toast lands in step 14.
    // eslint-disable-next-line no-console
    console.error('follow toggle failed', e)
  }
}
</script>

<template>
  <button
    type="button"
    :class="[
      'btn',
      followed ? 'border-rose-300 text-rose-600 dark:border-rose-700 dark:text-rose-300' : '',
    ]"
    :aria-pressed="followed"
    @click="toggle"
  >
    <Heart
      :class="['size-4', followed ? 'fill-rose-500 stroke-rose-500' : '']"
    />
    {{ followed ? 'Seguito' : 'Segui' }}
  </button>
</template>
