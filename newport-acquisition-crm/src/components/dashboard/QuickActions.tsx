import { FileSpreadsheet, ListPlus, Plus, ScrollText } from 'lucide-react'

interface QuickActionsProps {
  onAction: (action: string) => void
}

const ACTIONS = [
  { id: 'new-opportunity', label: 'New Opportunity', icon: Plus },
  { id: 'add-task', label: 'Add Task', icon: ListPlus },
  { id: 'log-activity', label: 'Log Activity', icon: ScrollText },
  { id: 'import-excel', label: 'Import Excel', icon: FileSpreadsheet },
] as const

export function QuickActions({ onAction }: QuickActionsProps) {
  return (
    <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
      <h2 className="font-brand text-lg font-bold text-navy-900">Quick Actions</h2>
      <p className="mt-0.5 mb-4 text-sm text-ink-muted">Common workflows — prototype only</p>
      <div className="grid grid-cols-2 gap-2">
        {ACTIONS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => onAction(id)}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-canvas px-3 py-2.5 text-left text-sm font-medium text-ink transition-colors hover:border-accent-muted hover:bg-accent-soft"
          >
            <Icon className="h-4 w-4 shrink-0 text-accent" strokeWidth={1.75} />
            {label}
          </button>
        ))}
      </div>
    </section>
  )
}
