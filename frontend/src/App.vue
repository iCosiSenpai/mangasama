<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Toaster } from 'vue-sonner'
import 'vue-sonner/style.css'
import AppShell from '@/components/AppShell.vue'

const route = useRoute()
// The login screen renders standalone (no sidebar/header).
const bare = computed(() => route.name === 'login')
</script>

<template>
  <RouterView v-if="bare" />
  <AppShell v-else />
  <Toaster position="top-right" rich-colors />
</template>
