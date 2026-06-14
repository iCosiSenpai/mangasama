<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Moon, Search, Sun } from 'lucide-vue-next'
import Sidebar from './Sidebar.vue'

const dark = ref(true)

onMounted(() => {
  dark.value = document.documentElement.classList.contains('dark')
})

function toggleTheme(): void {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
}
</script>

<template>
  <div class="flex h-full">
    <Sidebar />
    <main class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <header
        class="flex h-12 items-center justify-end gap-2 border-b border-slate-200 px-4 dark:border-slate-800"
      >
        <RouterLink
          to="/search"
          class="btn"
          active-class="nav-active"
        >
          <Search class="size-4" />
          Cerca
        </RouterLink>
        <button
          type="button"
          class="btn"
          :aria-label="dark ? 'Switch to light theme' : 'Switch to dark theme'"
          @click="toggleTheme"
        >
          <Sun v-if="dark" class="size-4" />
          <Moon v-else class="size-4" />
        </button>
      </header>
      <section class="flex-1 overflow-y-auto p-6">
        <div class="mx-auto max-w-7xl">
          <RouterView />
        </div>
      </section>
      <footer
        class="border-t border-slate-200 px-6 py-3 text-xs text-slate-500 dark:border-slate-800"
      >
        MangaSama · step 9
      </footer>
    </main>
  </div>
</template>
