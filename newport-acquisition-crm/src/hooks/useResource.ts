import { useCallback, useEffect, useRef, useState } from 'react'
import { getStoredSession } from '@/lib/api'
import { appendDemoChange, loadDemoCollection, saveDemoCollection } from '@/lib/demoStore'

const API_BASE = '/api/resources'

function isLocalDemo() {
  return getStoredSession()?.token === 'local-demo'
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredSession()?.token
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { error?: string }).error || `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

export interface ResourceApi<T extends { id: string }> {
  items: T[]
  loading: boolean
  error: string | null
  save: (id: string, patch: Partial<T>) => Promise<T>
  create: (data: Partial<T>) => Promise<T>
  refresh: () => Promise<void>
}

/**
 * Loads a CRM module collection from the database API.
 * In local-demo (static hosting) mode, edits persist in localStorage so
 * reopening the share link keeps every change.
 */
export function useResource<T extends { id: string }>(
  resource: string,
  mock: T[],
): ResourceApi<T> {
  const [items, setItems] = useState<T[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const localMode = useRef(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    if (isLocalDemo()) {
      localMode.current = true
      setItems(loadDemoCollection(resource, mock))
      setLoading(false)
      return
    }
    try {
      const data = await request<T[]>(`/${resource}`)
      localMode.current = false
      setItems(data)
    } catch (err) {
      localMode.current = true
      setItems(loadDemoCollection(resource, mock))
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [resource, mock])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const save = useCallback(
    async (id: string, patch: Partial<T>) => {
      if (localMode.current) {
        let merged: T | undefined
        setItems((prev) => {
          const next = prev.map((item) => {
            if (item.id !== id) return item
            merged = { ...item, ...patch }
            return merged
          })
          saveDemoCollection(resource, next)
          return next
        })
        if (!merged) throw new Error('Record not found')
        appendDemoChange({
          resourceType: resource,
          resourceId: id,
          changeType: 'update',
          changedFields: Object.keys(patch),
          actorName: 'Dennis DiCapua',
          createdAt: new Date().toISOString(),
        })
        return merged
      }
      const updated = await request<T>(`/${resource}/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      })
      setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...updated } : item)))
      return updated
    },
    [resource],
  )

  const create = useCallback(
    async (data: Partial<T>) => {
      if (localMode.current) {
        const record = {
          ...data,
          id: `${resource}_local_${Date.now()}`,
        } as T
        setItems((prev) => {
          const next = [record, ...prev]
          saveDemoCollection(resource, next)
          return next
        })
        appendDemoChange({
          resourceType: resource,
          resourceId: record.id,
          changeType: 'create',
          changedFields: Object.keys(data),
          actorName: 'Dennis DiCapua',
          createdAt: new Date().toISOString(),
        })
        return record
      }
      const created = await request<T>(`/${resource}`, {
        method: 'POST',
        body: JSON.stringify(data),
      })
      setItems((prev) => [created, ...prev])
      return created
    },
    [resource],
  )

  return { items, loading, error, save, create, refresh }
}
