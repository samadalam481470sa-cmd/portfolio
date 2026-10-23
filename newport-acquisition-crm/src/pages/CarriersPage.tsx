import { useResource } from '@/hooks/useResource'
import { ResourceWorkspace } from '@/components/shared/ResourceWorkspace'
import { CARRIER_STATUSES, mockCarriers, type CarrierRecord } from '@/data/mockModules'

export function CarriersPage() {
  const api = useResource<CarrierRecord>('carriers', mockCarriers)

  return (
    <ResourceWorkspace<CarrierRecord>
      title="Carriers / Reinsurers"
      description="Capacity partners across the portfolio and active deal pipeline."
      api={api}
      searchKeys={['name', 'kind', 'lines', 'contactName']}
      columns={[
        { key: 'name', label: 'Name' },
        { key: 'kind', label: 'Type' },
        { key: 'amBestRating', label: 'AM Best' },
        { key: 'lines', label: 'Lines' },
        {
          key: 'capacityStatus',
          label: 'Capacity Status',
          render: (c) => (
            <span
              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                c.capacityStatus === 'Active'
                  ? 'bg-success-bg text-success'
                  : c.capacityStatus === 'In Discussion'
                    ? 'bg-accent-soft text-navy-800'
                    : 'bg-warning-bg text-warning'
              }`}
            >
              {c.capacityStatus}
            </span>
          ),
        },
      ]}
      statusKey="capacityStatus"
      statusOptions={CARRIER_STATUSES}
      fields={[
        { key: 'name', label: 'Name', type: 'text' },
        { key: 'kind', label: 'Type', type: 'select', options: ['Carrier', 'Reinsurer'] },
        { key: 'amBestRating', label: 'AM Best rating', type: 'text' },
        { key: 'lines', label: 'Lines of business', type: 'text' },
        { key: 'contactName', label: 'Contact name', type: 'text' },
        { key: 'contactEmail', label: 'Contact email', type: 'text' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
      ]}
      itemTitle={(c) => c.name || 'New carrier'}
      itemSubtitle={(c) => [c.kind, c.amBestRating && `AM Best ${c.amBestRating}`].filter(Boolean).join(' · ')}
      newRecord={() => ({
        name: 'New Carrier',
        kind: 'Carrier',
        amBestRating: '',
        lines: '',
        capacityStatus: 'In Discussion',
        contactName: '',
        contactEmail: '',
        notes: '',
      })}
    />
  )
}
