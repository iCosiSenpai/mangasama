<script setup lang="ts">
import { Heart } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useSeriesStore } from '@/stores/series'

const props = defineProps<{
  seriesId: number
  followed: boolean
}>()

const store = useSeriesStore()

async function toggle(): Promise<void> {
  const next = !props.followed
  try {
    await store.setFollowed(props.seriesId, next)
    toast.success(next ? 'Serie seguita' : 'Non più seguita')
  } catch {
    toast.error('Operazione follow fallita')
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
