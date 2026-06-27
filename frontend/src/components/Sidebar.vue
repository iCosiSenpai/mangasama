<script setup lang="ts">
import { onMounted } from 'vue'
import { BookMarked, Briefcase, Heart, Home, Library, Search, Settings } from 'lucide-vue-next'
import { useLibrariesStore } from '@/stores/libraries'
import ProviderStatusBadge from './ProviderStatusBadge.vue'

const store = useLibrariesStore()

onMounted(() => {
  void store.load()
})
</script>

<template>
  <aside
    class="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
    aria-label="Barra laterale"
  >
    <div
      class="flex h-12 items-center gap-2 border-b border-slate-200 px-4 font-semibold dark:border-slate-800"
    >
      <BookMarked class="size-4 text-brand-600" />
      MangaSama
    </div>

    <nav class="flex-1 space-y-1 overflow-y-auto p-2" aria-label="Navigazione principale">
      <RouterLink to="/" class="nav-item" active-class="nav-active" exact-active-class="nav-active">
        <Home class="size-4" />
        Librerie
      </RouterLink>

      <RouterLink
        v-for="lib in store.items"
        :key="lib.id"
        :to="`/library/${lib.id}`"
        class="nav-item"
        active-class="nav-active"
      >
        <Library class="size-4" />
        <span class="flex-1 truncate">{{ lib.name }}</span>
        <span class="text-xs text-slate-500 dark:text-slate-400">
          {{ lib.series_count }}
        </span>
      </RouterLink>

      <hr class="my-2 border-slate-200 dark:border-slate-800" />

      <RouterLink to="/search" class="nav-item" active-class="nav-active">
        <Search class="size-4" />
        Cerca
      </RouterLink>
      <RouterLink to="/follow" class="nav-item" active-class="nav-active">
        <Heart class="size-4" />
        Seguiti
      </RouterLink>
      <RouterLink to="/jobs" class="nav-item" active-class="nav-active">
        <Briefcase class="size-4" />
        Jobs
      </RouterLink>
      <RouterLink to="/settings" class="nav-item" active-class="nav-active">
        <Settings class="size-4" />
        Settings
      </RouterLink>
    </nav>

    <div
      class="flex items-center gap-2 border-t border-slate-200 p-3 text-xs text-slate-500 dark:border-slate-800"
    >
      <ProviderStatusBadge />
      <span>Provider status</span>
    </div>
  </aside>
</template>
