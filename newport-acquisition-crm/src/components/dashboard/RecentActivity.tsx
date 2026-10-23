import {
  ArrowRightLeft,
  FileUp,
  MessageSquare,
  RefreshCw,
  StickyNote,
} from 'lucide-react'
import type { ActivityItem } from '@/types'
import { formatRelativeTime } from '@/utils/dashboard'
import type { LucideIcon } from 'lucide-react'

interface RecentActivityProps {
  items: ActivityItem[]
}

const TYPE_ICONS: Record<ActivityItem['type'], LucideIcon> = {
  stage_change: ArrowRightLeft,
  note: StickyNote,
  document: FileUp,
  status_change: RefreshCw,
  update: MessageSquare,
}

export function RecentActivity({ items }: RecentActivityProps) {
  return (
    <section className="rounded-xl border border-border bg-surface shadow-(--shadow-card)">
      <div className="border-b border-border px-5 py-4">
        <h2 className="font-brand text-lg font-bold text-navy-900">Recent Activity</h2>
        <p className="mt-0.5 text-sm text-ink-muted">Latest updates across the Newport team</p>
      </div>

      <ul className="divide-y divide-border/70">
        {items.map((item) => {
          const Icon = TYPE_ICONS[item.type]
          return (
            <li key={item.id} className="flex gap-3 px-5 py-3.5">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
                <Icon className="h-4 w-4" strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-ink">
                  {item.actor ? (
                    <>
                      <span className="font-semibold">{item.actor}</span> {item.message}
                    </>
                  ) : (
                    item.message
                  )}
                </p>
                <p className="mt-0.5 text-xs text-ink-subtle">
                  {formatRelativeTime(item.timestamp)}
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
