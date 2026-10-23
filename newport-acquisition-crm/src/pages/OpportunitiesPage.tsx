import { useMemo, useState } from 'react'
import { useData } from '@/data/DataContext'
import { OpportunityEditor } from '@/components/shared/OpportunityEditor'
import { OPPORTUNITY_STATUSES } from '@/data/constants'
import { formatCurrency } from '@/utils/dashboard'
import type { OpportunityStatus } from '@/types'

export function OpportunitiesPage() {
  const { opportunities, loading, saveOpportunity } = useData()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<'All' | OpportunityStatus>('All')

  const filtered = useMemo(() => {
    if (statusFilter === 'All') return opportunities
    return opportunities.filter((o) => o.status === statusFilter)
  }, [opportunities, statusFilter])

  const selected =
    opportunities.find((o) => o.id === selectedId) ?? filtered[0] ?? null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b border-border bg-surface px-6 py-5 lg:px-8">
        <h1 className="font-brand text-2xl font-bold text-navy-900">Opportunities</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Edit deal status, entity details, and the full acquisition record — one-stop view for
          Dennis and the team.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-canvas px-6 py-3 lg:px-8">
        <span className="text-xs font-semibold tracking-[0.06em] text-ink-subtle uppercase">
          Status
        </span>
        <button
          type="button"
          onClick={() => setStatusFilter('All')}
          className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
            statusFilter === 'All'
              ? 'border-navy-900 bg-navy-900 text-white'
              : 'border-border bg-surface text-ink-muted'
          }`}
        >
          All
        </button>
        {OPPORTUNITY_STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
              statusFilter === s
                ? 'border-navy-900 bg-navy-900 text-white'
                : 'border-border bg-surface text-ink-muted'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[1fr_420px]">
        <div className="custom-scroll overflow-auto border-r border-border">
          {loading && (
            <p className="px-6 py-8 text-sm text-ink-muted">Loading from database…</p>
          )}
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="sticky top-0 bg-canvas text-[11px] tracking-[0.06em] text-ink-subtle uppercase">
              <tr className="border-b border-border">
                <th className="px-5 py-3 font-semibold">Project #</th>
                <th className="px-3 py-3 font-semibold">Project</th>
                <th className="px-3 py-3 font-semibold">Entity</th>
                <th className="px-3 py-3 font-semibold">Status</th>
                <th className="px-3 py-3 font-semibold">Stage</th>
                <th className="px-5 py-3 text-right font-semibold">NWP</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((opp) => {
                const active = selected?.id === opp.id
                return (
                  <tr
                    key={opp.id}
                    onClick={() => setSelectedId(opp.id)}
                    className={`cursor-pointer border-b border-border/70 ${
                      active ? 'bg-accent-soft/60' : 'hover:bg-accent-soft/30'
                    }`}
                  >
                    <td className="px-5 py-3.5 font-semibold text-navy-900">
                      Project {opp.projectNumber}
                    </td>
                    <td className="px-3 py-3.5 font-medium text-ink">{opp.projectName}</td>
                    <td className="px-3 py-3.5 text-ink-muted">{opp.entityName}</td>
                    <td className="px-3 py-3.5">
                      <span className="rounded-md bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-navy-800">
                        {opp.status}
                      </span>
                    </td>
                    <td className="px-3 py-3.5 text-ink">{opp.stage}</td>
                    <td className="px-5 py-3.5 text-right tabular-nums">
                      {formatCurrency(opp.nwp)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <aside className="min-h-[480px] bg-surface lg:h-[calc(100vh-11rem)]">
          {selected ? (
            <OpportunityEditor
              opportunity={selected}
              onSave={(patch) => saveOpportunity(selected.id, patch).then(() => undefined)}
            />
          ) : (
            <p className="p-6 text-sm text-ink-muted">Select an opportunity to edit.</p>
          )}
        </aside>
      </div>
    </div>
  )
}
