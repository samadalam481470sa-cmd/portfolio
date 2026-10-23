/**
 * Persistent local demo store for static hosting (GitHub Pages / CDN).
 * Saves CRM data in localStorage so edits survive closing and reopening the link.
 */

const PREFIX = 'newport_crm_demo_v1_'

function key(name: string) {
  return `${PREFIX}${name}`
}

export function loadDemoCollection<T>(name: string, fallback: T[]): T[] {
  try {
    const raw = localStorage.getItem(key(name))
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? (parsed as T[]) : fallback
  } catch {
    return fallback
  }
}

export function saveDemoCollection<T>(name: string, items: T[]): void {
  try {
    localStorage.setItem(key(name), JSON.stringify(items))
  } catch {
    // Quota / private mode — ignore; in-memory still works for the session
  }
}

export function appendDemoChange(entry: {
  resourceType: string
  resourceId: string
  changeType: string
  changedFields: string[]
  actorName: string
  createdAt: string
}): void {
  try {
    const existing = loadDemoCollection<typeof entry>('change_history', [])
    saveDemoCollection('change_history', [entry, ...existing].slice(0, 500))
  } catch {
    // ignore
  }
}

export function loadDemoChangeHistory() {
  return loadDemoCollection<{
    resourceType: string
    resourceId: string
    changeType: string
    changedFields: string[]
    actorName: string
    createdAt: string
  }>('change_history', [])
}
