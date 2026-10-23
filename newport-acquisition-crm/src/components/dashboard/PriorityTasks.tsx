import type { PriorityTask, TaskPriority } from '@/types'
import { formatDate } from '@/utils/dashboard'

interface PriorityTasksProps {
  tasks: PriorityTask[]
  onProjectClick?: (projectId: string) => void
}

const PRIORITY_STYLES: Record<TaskPriority, string> = {
  A: 'bg-navy-900 text-white',
  B: 'bg-accent-soft text-navy-800',
  C: 'bg-canvas text-ink-muted border border-border',
}

const PRIORITY_LABELS: Record<TaskPriority, string> = {
  A: 'Must move this week',
  B: 'Important but can wait',
  C: 'Monitor only',
}

export function PriorityTasks({ tasks, onProjectClick }: PriorityTasksProps) {
  return (
    <section className="flex h-full flex-col rounded-xl border border-border bg-surface shadow-(--shadow-card)">
      <div className="border-b border-border px-5 py-4">
        <h2 className="font-brand text-lg font-bold text-navy-900">This Week&apos;s Priorities</h2>
        <p className="mt-0.5 text-sm text-ink-muted">A / B / C priority actions across the team</p>
      </div>

      <ul className="divide-y divide-border/70">
        {tasks.map((task) => (
          <li key={task.id} className="px-5 py-3.5">
            <div className="flex items-start gap-3">
              <span
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-bold ${PRIORITY_STYLES[task.priority]}`}
                title={PRIORITY_LABELS[task.priority]}
              >
                {task.priority}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">{task.action}</p>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-muted">
                  <button
                    type="button"
                    className="font-medium text-accent hover:underline"
                    onClick={() => onProjectClick?.(task.projectId)}
                  >
                    {task.projectName}
                  </button>
                  <span className="text-border-strong">·</span>
                  <span>{task.owner}</span>
                  <span className="text-border-strong">·</span>
                  <span>Due {formatDate(task.dueDate)}</span>
                </div>
              </div>
            </div>
          </li>
        ))}
      </ul>

      <div className="mt-auto border-t border-border px-5 py-3">
        <div className="flex flex-wrap gap-3 text-[11px] text-ink-subtle">
          <span>
            <strong className="text-navy-900">A</strong> Must move this week
          </span>
          <span>
            <strong className="text-navy-900">B</strong> Important but can wait
          </span>
          <span>
            <strong className="text-navy-900">C</strong> Monitor only
          </span>
        </div>
      </div>
    </section>
  )
}
