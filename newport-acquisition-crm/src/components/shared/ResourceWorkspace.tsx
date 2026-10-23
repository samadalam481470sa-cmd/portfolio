import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Plus, Search } from 'lucide-react'
import type { ResourceApi } from '@/hooks/useResource'

export interface FieldDef {
  key: string
  label: string
  type: 'text' | 'number' | 'date' | 'textarea' | 'select'
  options?: readonly string[]
  placeholder?: string
}

export interface ColumnDef<T> {
  key: keyof T & string
  label: string
  render?: (item: T) => ReactNode
  align?: 'left' | 'right'
}

interface ResourceWorkspaceProps<T extends { id: string }> {
  title: string
  description: string
  api: ResourceApi<T>
  columns: ColumnDef<T>[]
  fields: FieldDef[]
  statusKey: keyof T & string
  statusOptions: readonly string[]
  itemTitle: (item: T) => string
  itemSubtitle?: (item: T) => string
  newRecord: () => Partial<T>
  searchKeys: Array<keyof T & string>
}

/**
 * Standard two-pane module layout: record list on the left, editor on the
 * right. The status field is always pinned at the top of the editor.
 */
export function ResourceWorkspace<T extends { id: string }>({
  title,
  description,
  api,
  columns,
  fields,
  statusKey,
  statusOptions,
  itemTitle,
  itemSubtitle,
  newRecord,
  searchKeys,
}: ResourceWorkspaceProps<T>) {
  const { items, loading, save, create } = api
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return items
    return items.filter((item) =>
      searchKeys.some((key) => String(item[key] ?? '').toLowerCase().includes(q)),
    )
  }, [items, search, searchKeys])

  const selected = useMemo(
    () => items.find((i) => i.id === selectedId) ?? filtered[0] ?? null,
    [items, filtered, selectedId],
  )

  useEffect(() => {
    setDraft({})
    setMessage(null)
    setErrorMsg(null)
  }, [selected?.id])

  const fieldValue = (key: string): unknown => {
    if (key in draft) return draft[key]
    return selected ? (selected as Record<string, unknown>)[key] : ''
  }

  const setField = (key: string, value: unknown) => {
    setDraft((prev) => ({ ...prev, [key]: value }))
    setMessage(null)
  }

  const handleSave = async () => {
    if (!selected || Object.keys(draft).length === 0) {
      setMessage('No changes to save')
      return
    }
    setSaving(true)
    setErrorMsg(null)
    try {
      await save(selected.id, draft as Partial<T>)
      setDraft({})
      setMessage('Saved to database')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async () => {
    setErrorMsg(null)
    try {
      const created = await create(newRecord())
      setSelectedId(created.id)
      setMessage('New record created — fill in the details and save')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Create failed')
    }
  }

  const renderInput = (field: FieldDef) => {
    const value = fieldValue(field.key)
    const common =
      'mt-1 w-full rounded-lg border border-border bg-surface px-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20'

    if (field.type === 'select') {
      return (
        <select
          className={`${common} h-10`}
          value={String(value ?? '')}
          onChange={(e) => setField(field.key, e.target.value)}
        >
          {(field.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      )
    }
    if (field.type === 'textarea') {
      return (
        <textarea
          className={`${common} min-h-24 py-2`}
          value={String(value ?? '')}
          placeholder={field.placeholder}
          onChange={(e) => setField(field.key, e.target.value)}
        />
      )
    }
    return (
      <input
        type={field.type}
        className={`${common} h-10`}
        value={field.type === 'number' ? Number(value ?? 0) : String(value ?? '')}
        placeholder={field.placeholder}
        onChange={(e) =>
          setField(field.key, field.type === 'number' ? Number(e.target.value) : e.target.value)
        }
      />
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border bg-surface px-6 py-5 lg:px-8">
        <div>
          <h1 className="font-brand text-2xl font-bold text-navy-900">{title}</h1>
          <p className="mt-1 text-sm text-ink-muted">{description}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-ink-subtle" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`Search ${title.toLowerCase()}...`}
              className="h-10 w-56 rounded-lg border border-border bg-canvas pr-3 pl-9 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          </div>
          <button
            type="button"
            onClick={() => void handleCreate()}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-navy-900 px-3.5 text-sm font-semibold text-white hover:bg-navy-800"
          >
            <Plus className="h-4 w-4" strokeWidth={2} />
            New
          </button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[1fr_400px]">
        <div className="custom-scroll overflow-auto border-r border-border">
          {loading && <p className="px-6 py-8 text-sm text-ink-muted">Loading from database…</p>}
          {!loading && filtered.length === 0 && (
            <p className="px-6 py-8 text-sm text-ink-muted">No records match.</p>
          )}
          {!loading && filtered.length > 0 && (
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="sticky top-0 bg-canvas text-[11px] tracking-[0.06em] text-ink-subtle uppercase">
                <tr className="border-b border-border">
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      className={`px-4 py-3 font-semibold first:pl-6 last:pr-6 ${
                        col.align === 'right' ? 'text-right' : ''
                      }`}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const active = selected?.id === item.id
                  return (
                    <tr
                      key={item.id}
                      onClick={() => setSelectedId(item.id)}
                      className={`cursor-pointer border-b border-border/70 ${
                        active ? 'bg-accent-soft/60' : 'hover:bg-accent-soft/30'
                      }`}
                    >
                      {columns.map((col) => (
                        <td
                          key={col.key}
                          className={`px-4 py-3.5 first:pl-6 last:pr-6 ${
                            col.align === 'right' ? 'text-right tabular-nums' : ''
                          }`}
                        >
                          {col.render ? col.render(item) : String(item[col.key] ?? '—')}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        <aside className="flex min-h-[480px] flex-col bg-surface lg:h-[calc(100vh-8rem)]">
          {selected ? (
            <>
              <div className="border-b border-border px-5 py-4">
                <h2 className="font-brand text-lg font-bold text-navy-900">
                  {itemTitle(selected)}
                </h2>
                {itemSubtitle && (
                  <p className="mt-0.5 text-sm text-ink-muted">{itemSubtitle(selected)}</p>
                )}
              </div>

              <div className="custom-scroll flex-1 space-y-4 overflow-y-auto px-5 py-4">
                <div className="rounded-lg border border-accent-muted/60 bg-accent-soft/40 p-3">
                  <label className="text-[11px] font-semibold tracking-[0.06em] text-ink-muted uppercase">
                    Status (editable)
                  </label>
                  <select
                    value={String(fieldValue(statusKey) ?? '')}
                    onChange={(e) => setField(statusKey, e.target.value)}
                    className="mt-1.5 h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm font-medium outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
                  >
                    {statusOptions.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>

                {fields.map((field) => (
                  <label key={field.key} className="block">
                    <span className="text-[11px] font-semibold tracking-[0.06em] text-ink-muted uppercase">
                      {field.label}
                    </span>
                    {renderInput(field)}
                  </label>
                ))}
              </div>

              <div className="border-t border-border bg-canvas px-5 py-3">
                {errorMsg && <p className="mb-2 text-xs text-attention">{errorMsg}</p>}
                {message && <p className="mb-2 text-xs text-success">{message}</p>}
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void handleSave()}
                  className="h-10 w-full rounded-lg bg-navy-900 text-sm font-semibold text-white hover:bg-navy-800 disabled:opacity-60"
                >
                  {saving ? 'Saving…' : 'Save changes to database'}
                </button>
              </div>
            </>
          ) : (
            <p className="p-6 text-sm text-ink-muted">Select a record to edit.</p>
          )}
        </aside>
      </div>
    </div>
  )
}
