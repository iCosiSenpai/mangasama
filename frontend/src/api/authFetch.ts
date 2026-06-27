/** Helpers for authenticated fetch/download outside axios (SSE, blobs, img). */

const STORAGE_KEY = 'mangasama.auth'

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const cred = localStorage.getItem(STORAGE_KEY)
  const headers: Record<string, string> = { ...extra }
  if (cred) headers.Authorization = `Basic ${cred}`
  return headers
}

export async function downloadAuthenticated(url: string, filename: string): Promise<void> {
  const res = await fetch(url, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Download failed: HTTP ${res.status}`)
  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  a.click()
  URL.revokeObjectURL(objectUrl)
}

export async function fetchAuthenticatedBlob(url: string): Promise<string> {
  const res = await fetch(url, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Fetch failed: HTTP ${res.status}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}
