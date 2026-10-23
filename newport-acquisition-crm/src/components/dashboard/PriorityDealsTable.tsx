import type { Opportunity, OpportunityStatus } from '@/types'
import { formatCurrency, formatDate } from '@/utils/dashboard'

interface PriorityDealsTableProps {
  opportunities: Opportunity[]
  onSelect: (opportunity: Opportunity) => void
}

const STATUS_STYLES: Record<OpportunityStatus, string> = {
  Active: 'bg-success-bg text-success',
  Pending: 'bg-accent-soft text-accent-hover',
  Inactive: 'bg-canvas text-ink-muted',
  Closed: 'bg-canvas text-ink-muted',
  Declined: 'bg-canvas text-ink-subtle',
  Withdrew: 'bg-canvas text-ink-subtle',
  Completed: 'bg-success-bg text-success',
}

export function PriorityDealsTable({ opportunities, onSelect }: PriorityDealsTableProps) {
  return (
    <section className="rounded-xl border border-border bg-surface shadow-(--shadow-card)">
      <div className="flex items-end justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h2 className="font-brand text-lg font-bold text-navy-900">Priority Deals</h2>
          <p className="mt-0.5 text-sm text-ink-muted">
            Confidential project code names with key financials and next actions
          </p>
        </div>
      </div>

      <div className="custom-scroll overflow-x-auto">
        <table className="w-full min-w-[1100px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-canvas/80 text-[11px] tracking-[0.06em] text-ink-subtle uppercase">
              <th className="px-5 py-3 font-semibold">Project</th>
              <th className="px-3 py-3 font-semibold">Entity</th>
              <th className="px-3 py-3 font-semibold">Status</th>
              <th className="px-3 py-3 font-semibold">Stage</th>
              <th className="px-3 py-3 font-semibold">Deal Lead</th>
              <th className="px-3 py-3 text-right font-semibold">NWP</th>
              <th className="px-3 py-3 text-right font-semibold">Net Revenue</th>
              <th className="px-3 py-3 text-right font-semibold">PF EBITDA</th>
              <th className="px-3 py-3 font-semibold">Next Action</th>
              <th className="px-5 py-3 font-semibold">Next Action Date</th>
            </tr>
          </thead>
          <tbody>
            {opportunities.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-5 py-10 text-center text-sm text-ink-muted">
                  No opportunities match the current filters.
                </td>
              </tr>
            ) : (
              opportunities.map((opp) => (
                <tr
                  key={opp.id}
                  onClick={() => onSelect(opp)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelect(opp)
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  className="cursor-pointer border-b border-border/70 transition-colors last:border-0 hover:bg-accent-soft/40 focus-visible:bg-accent-soft/50 focus-visible:outline-none"
                >
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      {opp.needsAttention && (
                        <span
                          className="h-1.5 w-1.5 shrink-0 rounded-full bg-warning"
                          title="Needs attention"
                        />
                      )}
                      <span className="font-semibold text-navy-900">{opp.projectName}</span>
                    </div>
                  </td>
                  <td className="px-3 py-3.5 text-ink-muted">{opp.entityName}</td>
                  <td className="px-3 py-3.5">
                    <span
                      className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLES[opp.status]}`}
                    >
                      {opp.status}
                    </span>
                  </td>
                  <td className="px-3 py-3.5 font-medium text-ink">{opp.stage}</td>
                  <td className="px-3 py-3.5 text-ink-muted">{opp.dealLead || '—'}</td>
                  <td className="px-3 py-3.5 text-right font-medium tabular-nums text-ink">
                    {formatCurrency(opp.nwp)}
                  </td>
                  <td className="px-3 py-3.5 text-right tabular-nums text-ink-muted">
                    {formatCurrency(opp.netRevenue)}
                  </td>
                  <td className="px-3 py-3.5 text-right tabular-nums text-ink-muted">
                    {formatCurrency(opp.pfEbitda)}
                  </td>
                  <td className="max-w-[180px] truncate px-3 py-3.5 text-ink">
                    {opp.nextAction ?? (
                      <span className="text-warning italic">No next action</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap text-ink-muted">
                    {formatDate(opp.nextActionDate)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
