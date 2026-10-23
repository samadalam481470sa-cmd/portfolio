import { X } from 'lucide-react'
import { STATUS_FILTER_OPTIONS } from '@/data/constants'
import type { DashboardFilters, OpportunityStatus } from '@/types'

interface StatusFilterProps {
  filters: DashboardFilters
  onStatusChange: (status: DashboardFilters['status']) => void
  onClear: () => void
  hasFilters: boolean
  resultCount: number
}

export function StatusFilter({
  filters,
  onStatusChange,
  onClear,
  hasFilters,
  resultCount,
}: StatusFilterProps) {
  const options =
    filters.status === 'Needs Attention'
      ? ([...STATUS_FILTER_OPTIONS, 'Needs Attention'] as const)
      : STATUS_FILTER_OPTIONS

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs font-semibold tracking-[0.06em] text-ink-subtle uppercase">
          Status
        </span>
        {options.map((option) => {
          const active = filters.status === option
          const isAttention = option === 'Needs Attention'
          return (
            <button
              key={option}
              type="button"
              onClick={() =>
                onStatusChange(
                  option === 'All Deals'
                    ? 'All Deals'
                    : option === 'Needs Attention'
                      ? 'Needs Attention'
                      : (option as OpportunityStatus),
                )
              }
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                active
                  ? isAttention
                    ? 'border-attention bg-attention-bg text-attention'
                    : 'border-navy-900 bg-navy-900 text-white'
                  : 'border-border bg-surface text-ink-muted hover:border-border-strong hover:text-ink'
              }`}
            >
              {option}
            </button>
          )
        })}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-xs text-ink-subtle">
          {resultCount} opportunit{resultCount === 1 ? 'y' : 'ies'}
          {filters.stage ? ` · ${filters.stage}` : ''}
        </span>
        {hasFilters && (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex items-center gap-1 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:bg-canvas hover:text-ink"
          >
            <X className="h-3.5 w-3.5" strokeWidth={2} />
            Clear Filters
          </button>
        )}
      </div>
    </div>
  )
}
