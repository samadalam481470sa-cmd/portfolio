import type { AuthUser, Opportunity, OpportunityUpdate } from '@/types'

const TOKEN_KEY = 'newport_crm_session_token'
const USER_KEY = 'newport_crm_session_user'

const API_BASE = '/api'

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY)
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  headers.set('X-Requested-With', 'XMLHttpRequest')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { error?: string }).error || `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

export function getStoredSession(): { token: string; user: AuthUser } | null {
  const token = sessionStorage.getItem(TOKEN_KEY)
  const raw = sessionStorage.getItem(USER_KEY)
  if (!token || !raw) return null
  try {
    return { token, user: JSON.parse(raw) as AuthUser }
  } catch {
    return null
  }
}

export function storeSession(token: string, user: AuthUser) {
  sessionStorage.setItem(TOKEN_KEY, token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
}

export async function demoSignIn() {
  const data = await apiFetch<{ token: string; user: AuthUser; notice: string }>('/auth/demo', {
    method: 'POST',
    body: '{}',
  })
  storeSession(data.token, data.user)
  return data
}

export async function apiKeySignIn(apiKey: string) {
  const data = await apiFetch<{ token: string; user: AuthUser }>('/auth/api-key', {
    method: 'POST',
    body: JSON.stringify({ apiKey }),
  })
  storeSession(data.token, data.user)
  return data
}

export async function signOut() {
  try {
    await apiFetch('/auth/signout', { method: 'POST', body: '{}' })
  } catch {
    // ignore network errors on sign-out
  }
  clearSession()
}

export async function fetchOpportunities() {
  return apiFetch<Opportunity[]>('/opportunities')
}

export async function updateOpportunity(id: string, patch: OpportunityUpdate) {
  return apiFetch<Opportunity>(`/opportunities/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export async function fetchApiKeySlots() {
  return apiFetch<{
    slots: Array<{
      id: string
      slot: number
      label: string
      key_prefix: string
      status: string
      last_used_at: string | null
    }>
    capacity: number
    note: string
  }>('/security/api-keys')
}

/**
 * Download helpers — database is accessible anywhere (via link) and
 * downloadable everywhere (CSV for Excel, JSON for integrations, full .db file).
 */
async function downloadFile(path: string) {
  const token = sessionStorage.getItem(TOKEN_KEY)
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { error?: string }).error || `Download failed (${res.status})`)
  }
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const filename = match?.[1] ?? 'newport-export'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function downloadOpportunitiesCsv() {
  return downloadFile('/export/opportunities.csv')
}

export function downloadOpportunitiesJson() {
  return downloadFile('/export/opportunities.json')
}

export function downloadDatabaseFile() {
  return downloadFile('/export/database')
}

export async function fetchAuditLogs(limit = 40) {
  return apiFetch<
    Array<{
      id: string
      actor_name: string | null
      action: string
      resource_type: string
      resource_id: string | null
      detail: string
      created_at: string
    }>
  >(`/security/audit-logs?limit=${limit}`)
}

export interface ChangeHistoryEntry {
  id: string
  actorName: string | null
  apiKeySlot: number | null
  authMethod: string
  resourceType: string
  resourceId: string
  changeType: 'create' | 'update' | 'delete' | string
  changedFields: string[]
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  createdAt: string
}

export async function fetchChangeHistory(opts: {
  limit?: number
  slot?: number | null
  resourceType?: string | null
} = {}) {
  const params = new URLSearchParams()
  params.set('limit', String(opts.limit ?? 100))
  if (opts.slot) params.set('slot', String(opts.slot))
  if (opts.resourceType) params.set('resourceType', opts.resourceType)
  return apiFetch<{ count: number; changes: ChangeHistoryEntry[] }>(
    `/security/change-history?${params.toString()}`,
  )
}
