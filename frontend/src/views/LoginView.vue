<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { BookMarked, LogIn } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useAuthStore } from '@/stores/auth'
import { apiError } from '@/api/client'

const router = useRouter()
const auth = useAuthStore()

const password = ref('')
const loading = ref(false)

async function submit(): Promise<void> {
  if (!password.value || loading.value) return
  loading.value = true
  try {
    await auth.login(password.value)
    void router.push('/')
  } catch (e) {
    toast.error(apiError(e) || 'Password non valida')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-950">
    <form class="card w-full max-w-sm p-6" @submit.prevent="submit">
      <div class="mb-4 flex items-center gap-2 text-lg font-semibold">
        <BookMarked class="size-5 text-brand-600" />
        MangaSama
      </div>
      <p class="mb-4 text-sm text-slate-500 dark:text-slate-400">
        Inserisci la password admin per accedere.
      </p>
      <input
        v-model="password"
        type="password"
        autocomplete="current-password"
        placeholder="Password admin"
        class="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
      />
      <button type="submit" class="btn-primary mt-4 w-full justify-center" :disabled="!password || loading">
        <LogIn class="size-4" />
        Accedi
      </button>
    </form>
  </div>
</template>
