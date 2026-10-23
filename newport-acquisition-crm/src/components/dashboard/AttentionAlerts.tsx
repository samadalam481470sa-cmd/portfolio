import { AlertCircle, CalendarClock, Clock, UserX, Activity } from 'lucide-react'
import type { AttentionAlert, AttentionReason } from '@/types'
import type { LucideIcon } from 'lucide-react'

interface AttentionAlertsProps {
  alerts: AttentionAlert[]
  onProjectClick?: (projectId: string) => void
  onViewAll?: () => void
}

const ICONS: Record<AttentionReason, LucideIcon> = {
  'Next action overdue': Clock,
  'No next action assigned': AlertCircle,
  'No activity in 30+ days': Activity,
  'Upcoming deadline within 7 days': CalendarClock,
  'No deal owner assigned': UserX,
}

export function AttentionAlerts({ alerts, onProjectClick, onViewAll }: AttentionAlertsProps) {
  return (
    <section className="flex h-full flex-col rounded-xl border border-attention-border bg-surface shadow-(--shadow-card)">
      <div className="flex items-start justify-between gap-2 border-b border-attention-border/60 bg-attention-bg/50 px-5 py-4">
        <div>
          <h2 className="font-brand text-lg font-bold text-navy-900">Needs Attention</h2>
          <p className="mt-0.5 text-sm text-ink-muted">Items requiring executive follow-up</p>
        </div>
        {onViewAll && (
          <button
            type="button"
            onClick={onViewAll}
            className="text-xs font-semibold text-attention hover:underline"
          >
            View all
          </button>
        )}
      </div>

      <ul className="divide-y divide-border/70">
        {alerts.map((alert) => {
          const Icon = ICONS[alert.reason]
          return (
            <li key={alert.id} className="flex gap-3 px-5 py-3.5">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-warning-bg text-warning">
                <Icon className="h-4 w-4" strokeWidth={1.75} />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink">{alert.reason}</p>
                <button
                  type="button"
                  onClick={() => onProjectClick?.(alert.projectId)}
                  className="mt-0.5 text-sm font-medium text-accent hover:underline"
                >
                  {alert.projectName}
                </button>
                <p className="mt-0.5 text-xs text-ink-muted">{alert.detail}</p>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
