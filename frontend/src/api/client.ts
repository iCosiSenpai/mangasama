import axios, { AxiosError, type AxiosInstance } from 'axios'
import type { ApiErrorPayload } from '@/types/api'

/**
 * Shared axios instance.
 *
 * `baseURL: ''` so the request path is the absolute `/api/...`. In dev the
 * Vite proxy (`vite.config.ts`) routes that to `http://localhost:8000`. In
 * production the FastAPI app serves both the SPA and the API on the same
 * origin, so no proxy is needed.
 */
export const client: AxiosInstance = axios.create({
  baseURL: '',
  timeout: 15_000,
  headers: { Accept: 'application/json' },
})

// Request interceptor: keep room for an Authorization header in step 14.
// import { useAuthStore } from '@/stores/auth'
// client.interceptors.request.use((config) => {
//   const auth = useAuthStore()
//   if (auth.enabled && auth.token) {
//     config.headers.Authorization = `Bearer ${auth.token}`
//   }
//   return config
// })

// Response interceptor: normalize errors into `ApiErrorPayload` shape.
client.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status ?? 0
    // Auth gate: a 401 means the (optional) Basic gate rejected us — drop any
    // stale credential and bounce to the login screen. Dynamic imports avoid a
    // static import cycle (auth store → client; router → views → stores).
    if (status === 401) {
      localStorage.removeItem('mangasama.auth')
      delete client.defaults.headers.common.Authorization
      void import('@/router').then(({ router }) => {
        if (router.currentRoute.value.name !== 'login') {
          void router.push({ name: 'login' })
        }
      })
    }
    const data = (error.response?.data ?? {}) as {
      detail?: string
      type?: string
      errors?: unknown
    }
    const payload: ApiErrorPayload = {
      status,
      detail: data.detail ?? error.message ?? 'Network error',
      type: data.type ?? 'network_error',
      errors: data.errors,
      raw: error,
    }
    return Promise.reject(payload)
  },
)

/** Convenience helper for components that just want the message. */
export function apiError(e: unknown): string {
  if (e && typeof e === 'object' && 'detail' in e) {
    return String((e as { detail: unknown }).detail)
  }
  return e instanceof Error ? e.message : 'Unknown error'
}
