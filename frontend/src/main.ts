import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { initTheme } from '@/composables/useTheme'
import './style.css'

// Apply the persisted (or OS-preferred) theme before the first paint.
initTheme()

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Re-attach a persisted admin credential (if any) before the first request.
import { useAuthStore } from '@/stores/auth'
useAuthStore().hydrate()

app.mount('#app')
