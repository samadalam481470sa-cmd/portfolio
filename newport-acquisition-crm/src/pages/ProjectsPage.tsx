import { useMemo, useState } from 'react'
import { useData } from '@/data/DataContext'
import { OpportunityEditor } from '@/components/shared/OpportunityEditor'
import { formatCurrency } from '@/utils/dashboard'
import { FolderKanban } from 'lucide-react'

/**
 * Projects tab — acquisition projects labeled Project 1, Project 2, Project 3, etc.
 * Right panel has editable tabs; status is editable on every tab.
 */
export function ProjectsPage() {
  const { opportunities, loading, saveOpportunity } = useData()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const projects = useMemo(
    () =>
      [...opportunities].sort(
        (a, b) => (a.projectNumber ?? 0) - (b.projectNumber ?? 0),
      ),
    [opportunities],
  )

  const selected =
    projects.find((o) => o.id === selectedId) ?? projects[0] ?? null

  const rightTabs = [
    { id: 'overview', label: 'Snapshot' },
    { id: 'status', label: 'Status' },
    { id: 'entity', label: 'Entity' },
    { id: 'diligence', label: 'Diligence' },
    { id: 'actions', label: 'Outstanding' },
  ]

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b border-border bg-surface px-6 py-5 lg:px-8">
        <h1 className="font-brand text-2xl font-bold text-navy-900">Projects</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Project 1, Project 2, Project 3… — snapshot of where each acquisition stands and what is
          outstanding (counsel, accountant, diligence).
        </p>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[320px_1fr]">
        <div className="custom-scroll overflow-auto border-r border-border bg-canvas">
          {loading && <p className="px-4 py-6 text-sm text-ink-muted">Loading projects…</p>}
          <ul className="p-3">
            {projects.map((project) => {
              const active = selected?.id === project.id
              return (
                <li key={project.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(project.id)}
                    className={`mb-1.5 flex w-full items-start gap-3 rounded-xl border px-3 py-3 text-left transition-colors ${
                      active
                        ? 'border-accent bg-accent-soft'
                        : 'border-transparent bg-surface hover:border-border'
                    }`}
                  >
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-navy-900 text-white">
                      <FolderKanban className="h-4 w-4" strokeWidth={1.75} />
                    </div>
                    <div className="min-w-0">
                      <p className="font-semibold text-navy-900">
                        Project {project.projectNumber}
                      </p>
                      <p className="truncate text-xs text-ink-muted">{project.projectName}</p>
                      <p className="mt-1 text-[11px] text-ink-subtle">
                        {project.status} · {project.stage} · {formatCurrency(project.nwp)}
                      </p>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>

        <aside className="min-h-[480px] bg-surface lg:h-[calc(100vh-8rem)]">
          {selected ? (
            <OpportunityEditor
              opportunity={selected}
              tabs={rightTabs}
              onSave={(patch) => saveOpportunity(selected.id, patch).then(() => undefined)}
            />
          ) : (
            <p className="p-6 text-sm text-ink-muted">Select a project.</p>
          )}
        </aside>
      </div>
    </div>
  )
}
