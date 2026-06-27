<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  src: string
  alt?: string
  imgClass?: string
}>()

const blobUrl = ref<string | null>(null)
const failed = ref(false)

async function load(): Promise<void> {
  failed.value = false
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = null
  }
  try {
    const { fetchAuthenticatedBlob } = await import('@/api/authFetch')
    blobUrl.value = await fetchAuthenticatedBlob(props.src)
  } catch {
    failed.value = true
  }
}

watch(() => props.src, () => void load())

onMounted(() => void load())

onBeforeUnmount(() => {
  if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
})
</script>

<template>
  <img v-if="blobUrl" :src="blobUrl" :alt="alt" :class="imgClass" />
  <div
    v-else-if="failed"
    class="flex items-center justify-center bg-slate-100 text-xs text-slate-400 dark:bg-slate-800"
    :class="imgClass"
  >
    —
  </div>
</template>
