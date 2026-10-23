import type { AcquisitionStage } from '@/types'
import { formatCurrency } from '@/utils/dashboard'

interface PipelineStageData {
  stage: AcquisitionStage
  count: number
  nwp: number
}

interface PipelineOverviewProps {
  stages: PipelineStageData[]
  selectedStage: AcquisitionStage | null
  onSelectStage: (stage: AcquisitionStage | null) => void
}

export function PipelineOverview({
  stages,
  selectedStage,
  onSelectStage,
}: PipelineOverviewProps) {
  const maxCount = Math.max(...stages.map((s) => s.count), 1)
  const totalDeals = stages.reduce((sum, s) => sum + s.count, 0)

  return (
    <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="font-brand text-lg font-bold text-navy-900">Acquisition Pipeline</h2>
          <p className="mt-0.5 text-sm text-ink-muted">
            Active and pending opportunities by acquisition stage
          </p>
        </div>
        <p className="text-xs text-ink-subtle">{totalDeals} deals in view</p>
      </div>

      <div className="custom-scroll -mx-1 overflow-x-auto px-1 pb-1">
        <div className="flex min-w-[900px] gap-2">
          {stages.map((item, index) => {
            const isSelected = selectedStage === item.stage
            const barHeight = item.count === 0 ? 4 : Math.max(12, (item.count / maxCount) * 72)

            return (
              <button
                key={item.stage}
                type="button"
                onClick={() => onSelectStage(isSelected ? null : item.stage)}
                className={`group flex flex-1 flex-col rounded-lg border px-2.5 py-3 text-left transition-all ${
                  isSelected
                    ? 'border-accent bg-accent-soft shadow-(--shadow-card)'
                    : 'border-border bg-canvas/60 hover:border-accent-muted hover:bg-accent-soft/40'
                }`}
              >
                <div className="mb-3 flex h-[76px] items-end justify-center">
                  <div
                    className={`w-full max-w-[48px] rounded-t-md transition-all ${
                      isSelected
                        ? 'bg-accent'
                        : item.count === 0
                          ? 'bg-border'
                          : 'bg-navy-700 group-hover:bg-accent'
                    }`}
                    style={{ height: barHeight }}
                  />
                </div>

                <div className="flex items-baseline justify-between gap-1">
                  <span className="font-brand text-xl font-bold text-navy-900">{item.count}</span>
                  {item.nwp > 0 && (
                    <span className="text-[10px] font-medium text-ink-subtle">
                      {formatCurrency(item.nwp)}
                    </span>
                  )}
                </div>

                <p className="mt-1 text-[11px] leading-snug font-semibold text-ink">
                  {item.stage}
                </p>

                {index < stages.length - 1 && (
                  <span className="sr-only">Then proceeds to next stage</span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {selectedStage && (
        <p className="mt-3 text-xs text-accent">
          Filtering Priority Deals to <strong>{selectedStage}</strong>. Click the stage again to
          clear.
        </p>
      )}
    </section>
  )
}
