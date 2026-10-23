import { useResource } from '@/hooks/useResource'
import { ResourceWorkspace } from '@/components/shared/ResourceWorkspace'
import { SOURCE_TYPES } from '@/data/constants'
import { SOURCE_STATUSES, mockSources, type SourceRecord } from '@/data/mockModules'

export function SourcesPage() {
  const api = useResource<SourceRecord>('sources', mockSources)

  return (
    <ResourceWorkspace<SourceRecord>
      title="Sources / Bankers"
      description="Investment bankers, intermediaries, and partners who bring Newport deal flow."
      api={api}
      searchKeys={['name', 'firm', 'type']}
      columns={[
        { key: 'name', label: 'Name' },
        { key: 'firm', label: 'Firm' },
        { key: 'type', label: 'Type' },
        { key: 'dealsReferred', label: 'Deals Referred', align: 'right' },
        {
          key: 'status',
          label: 'Status',
          render: (s) => (
            <span
              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                s.status === 'Active' ? 'bg-success-bg text-success' : 'bg-canvas text-ink-muted'
              }`}
            >
              {s.status}
            </span>
          ),
        },
      ]}
      statusKey="status"
      statusOptions={SOURCE_STATUSES}
      fields={[
        { key: 'name', label: 'Name', type: 'text' },
        { key: 'firm', label: 'Firm', type: 'text' },
        { key: 'type', label: 'Source type', type: 'select', options: SOURCE_TYPES },
        { key: 'email', label: 'Email', type: 'text' },
        { key: 'phone', label: 'Phone', type: 'text' },
        { key: 'dealsReferred', label: 'Deals referred', type: 'number' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
      ]}
      itemTitle={(s) => s.name || 'New source'}
      itemSubtitle={(s) => [s.firm, s.type].filter(Boolean).join(' · ')}
      newRecord={() => ({
        name: 'New Source',
        firm: '',
        type: 'Investment Banker',
        email: '',
        phone: '',
        status: 'Active',
        dealsReferred: 0,
        notes: '',
      })}
    />
  )
}
