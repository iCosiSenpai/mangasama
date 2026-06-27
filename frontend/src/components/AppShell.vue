<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { LogOut, Moon, Search, Sun } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Sidebar from './Sidebar.vue'

const dark = ref(true)
const router = useRouter()
const auth = useAuthStore()

onMounted(() => {
  dark.value = document.documentElement.classList.contains('dark')
})

function toggleTheme(): void {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
}

function logout(): void {
  auth.logout()
  void router.push({ name: 'login' })
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
          v-if="auth.isAuthed"
          type="button"
          class="btn"
          title="Logout"
          @click="logout"
        >
          <LogOut class="size-4" />
        </button>
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
        MangaSama v0.1.0
      </footer>
    </main>
  </div>
</template>
