<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Toaster } from 'vue-sonner'
import 'vue-sonner/style.css'
import AppShell from '@/components/AppShell.vue'

const route = useRoute()
// The login and setup screens render standalone (no sidebar/header).
const bare = computed(() => route.name === 'login' || route.name === 'setup')
</script>

<template>
  <RouterView v-if="bare" />
  <AppShell v-else />
  <Toaster position="top-right" rich-colors />
</template>
