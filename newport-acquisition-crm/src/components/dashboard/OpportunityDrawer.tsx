import { useEffect } from 'react'
import { X } from 'lucide-react'
import type { Opportunity } from '@/types'
import { formatCurrency, formatDate } from '@/utils/dashboard'

interface OpportunityDrawerProps {
  opportunity: Opportunity | null
  onClose: () => void
}

export function OpportunityDrawer({ opportunity, onClose }: OpportunityDrawerProps) {
  useEffect(() => {
    if (!opportunity) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [opportunity, onClose])

  if (!opportunity) return null

  const fields: { label: string; value: string }[] = [
    { label: 'Entity', value: opportunity.entityName },
    { label: 'Status', value: opportunity.status },
    { label: 'Stage', value: opportunity.stage },
    { label: 'Deal Lead', value: opportunity.dealLead || 'Unassigned' },
    { label: 'Type', value: opportunity.type },
    { label: 'Specialty', value: opportunity.specialty },
    { label: 'Geography', value: opportunity.geography },
    { label: 'NWP', value: formatCurrency(opportunity.nwp) },
    { label: 'Net Revenue', value: formatCurrency(opportunity.netRevenue) },
    { label: 'PF EBITDA', value: formatCurrency(opportunity.pfEbitda) },
    { label: 'Next Action', value: opportunity.nextAction ?? 'None assigned' },
    { label: 'Next Action Date', value: formatDate(opportunity.nextActionDate) },
  ]

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        className="absolute inset-0 bg-navy-950/40 backdrop-blur-[2px]"
        aria-label="Close opportunity details"
        onClick={onClose}
      />
      <aside
        className="relative flex h-full w-full max-w-md animate-[slideIn_200ms_ease-out] flex-col bg-surface shadow-(--shadow-drawer)"
        role="dialog"
        aria-modal="true"
        aria-labelledby="opportunity-drawer-title"
      >
        <div className="flex items-start justify-between border-b border-border px-5 py-4">
          <div>
            <p className="text-[11px] font-semibold tracking-[0.1em] text-accent uppercase">
              Opportunity
            </p>
            <h2
              id="opportunity-drawer-title"
              className="mt-1 font-brand text-xl font-bold text-navy-900"
            >
              {opportunity.projectName}
            </h2>
            <p className="mt-0.5 text-sm text-ink-muted">{opportunity.entityName}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-ink-muted transition-colors hover:bg-canvas hover:text-ink"
            aria-label="Close"
          >
            <X className="h-5 w-5" strokeWidth={1.75} />
          </button>
        </div>

        <div className="custom-scroll flex-1 overflow-y-auto px-5 py-4">
          <dl className="space-y-3">
            {fields.map((field) => (
              <div
                key={field.label}
                className="grid grid-cols-[120px_1fr] gap-3 border-b border-border/70 pb-3 last:border-0"
              >
                <dt className="text-xs font-semibold tracking-[0.04em] text-ink-subtle uppercase">
                  {field.label}
                </dt>
                <dd className="text-sm font-medium text-ink">{field.value}</dd>
              </div>
            ))}
          </dl>

          {opportunity.needsAttention && opportunity.attentionReasons.length > 0 && (
            <div className="mt-4 rounded-lg border border-attention-border bg-attention-bg p-3">
              <p className="text-xs font-semibold text-attention">Needs Attention</p>
              <ul className="mt-1.5 space-y-1">
                {opportunity.attentionReasons.map((reason) => (
                  <li key={reason} className="text-sm text-ink">
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="border-t border-border bg-canvas px-5 py-4">
          <p className="text-center text-sm font-medium text-ink-muted">
            Full Opportunity Profile — Coming in next sprint
          </p>
        </div>
      </aside>

      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0.6; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
