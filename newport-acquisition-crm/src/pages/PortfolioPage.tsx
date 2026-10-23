import { useResource } from '@/hooks/useResource'
import { ResourceWorkspace } from '@/components/shared/ResourceWorkspace'
import { formatCurrency } from '@/utils/dashboard'
import {
  INTEGRATION_STATUSES,
  mockPortfolio,
  type PortfolioRecord,
} from '@/data/mockModules'

export function PortfolioPage() {
  const api = useResource<PortfolioRecord>('portfolio', mockPortfolio)

  return (
    <ResourceWorkspace<PortfolioRecord>
      title="Portfolio Companies"
      description="Completed acquisitions and their integration status."
      api={api}
      searchKeys={['name', 'specialty', 'dealLead']}
      columns={[
        { key: 'name', label: 'Company' },
        { key: 'specialty', label: 'Specialty' },
        { key: 'acquiredDate', label: 'Acquired' },
        {
          key: 'nwp',
          label: 'NWP',
          align: 'right',
          render: (p) => formatCurrency(p.nwp),
        },
        {
          key: 'pfEbitda',
          label: 'PF EBITDA',
          align: 'right',
          render: (p) => formatCurrency(p.pfEbitda),
        },
        {
          key: 'integrationStatus',
          label: 'Integration',
          render: (p) => (
            <span
              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                p.integrationStatus === 'Integrated'
                  ? 'bg-success-bg text-success'
                  : 'bg-accent-soft text-navy-800'
              }`}
            >
              {p.integrationStatus}
            </span>
          ),
        },
      ]}
      statusKey="integrationStatus"
      statusOptions={INTEGRATION_STATUSES}
      fields={[
        { key: 'name', label: 'Company name', type: 'text' },
        { key: 'acquiredDate', label: 'Acquired date', type: 'date' },
        { key: 'specialty', label: 'Specialty', type: 'text' },
        { key: 'geography', label: 'Geography', type: 'text' },
        { key: 'nwp', label: 'NWP (USD)', type: 'number' },
        { key: 'pfEbitda', label: 'PF EBITDA (USD)', type: 'number' },
        { key: 'dealLead', label: 'Deal lead', type: 'text' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
      ]}
      itemTitle={(p) => p.name || 'New portfolio company'}
      itemSubtitle={(p) =>
        [p.specialty, p.acquiredDate && `Acquired ${p.acquiredDate}`].filter(Boolean).join(' · ')
      }
      newRecord={() => ({
        name: 'New Portfolio Company',
        acquiredDate: null,
        specialty: '',
        geography: '',
        nwp: 0,
        pfEbitda: 0,
        integrationStatus: 'Integrating',
        dealLead: '',
        notes: '',
      })}
    />
  )
}
