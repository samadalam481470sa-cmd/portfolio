import { useResource } from '@/hooks/useResource'
import { ResourceWorkspace } from '@/components/shared/ResourceWorkspace'
import { TASK_STATUSES, mockTasksDb, type TaskRecord } from '@/data/mockModules'

const PRIORITY_BADGES: Record<string, string> = {
  A: 'bg-navy-900 text-white',
  B: 'bg-accent-soft text-navy-800',
  C: 'bg-canvas text-ink-muted border border-border',
}

export function TasksPage() {
  const api = useResource<TaskRecord>('tasks', mockTasksDb)

  return (
    <ResourceWorkspace<TaskRecord>
      title="Tasks & Follow-Ups"
      description="A = must move this week · B = important but can wait · C = monitor only."
      api={api}
      searchKeys={['action', 'projectName', 'owner']}
      columns={[
        {
          key: 'priority',
          label: 'Pri',
          render: (t) => (
            <span
              className={`inline-flex h-6 w-6 items-center justify-center rounded-md text-xs font-bold ${PRIORITY_BADGES[t.priority] ?? PRIORITY_BADGES.C}`}
            >
              {t.priority}
            </span>
          ),
        },
        { key: 'action', label: 'Action' },
        { key: 'projectName', label: 'Project' },
        { key: 'owner', label: 'Owner' },
        { key: 'dueDate', label: 'Due' },
        {
          key: 'status',
          label: 'Status',
          render: (t) => (
            <span
              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                t.status === 'Done'
                  ? 'bg-success-bg text-success'
                  : t.status === 'In Progress'
                    ? 'bg-accent-soft text-navy-800'
                    : 'bg-warning-bg text-warning'
              }`}
            >
              {t.status}
            </span>
          ),
        },
      ]}
      statusKey="status"
      statusOptions={TASK_STATUSES}
      fields={[
        { key: 'action', label: 'Action', type: 'text' },
        { key: 'priority', label: 'Priority', type: 'select', options: ['A', 'B', 'C'] },
        { key: 'projectName', label: 'Project', type: 'text' },
        { key: 'owner', label: 'Owner', type: 'text' },
        { key: 'dueDate', label: 'Due date', type: 'date' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
      ]}
      itemTitle={(t) => t.action || 'New task'}
      itemSubtitle={(t) => [t.projectName, t.owner].filter(Boolean).join(' · ')}
      newRecord={() => ({
        priority: 'B',
        action: 'New task',
        opportunityId: null,
        projectName: '',
        owner: '',
        dueDate: null,
        status: 'Open',
        notes: '',
      })}
    />
  )
}
