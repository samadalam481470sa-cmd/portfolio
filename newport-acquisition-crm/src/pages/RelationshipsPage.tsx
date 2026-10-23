import { useResource } from '@/hooks/useResource'
import { ResourceWorkspace } from '@/components/shared/ResourceWorkspace'
import {
  CONTACT_CATEGORIES,
  CONTACT_STATUSES,
  mockContacts,
  type ContactRecord,
} from '@/data/mockModules'

export function RelationshipsPage() {
  const api = useResource<ContactRecord>('contacts', mockContacts)

  return (
    <ResourceWorkspace<ContactRecord>
      title="Relationships"
      description="Management teams, bankers, counsel, and accountants across the deal book."
      api={api}
      searchKeys={['name', 'company', 'projectName', 'category']}
      columns={[
        { key: 'name', label: 'Name' },
        { key: 'company', label: 'Company' },
        { key: 'category', label: 'Category' },
        { key: 'projectName', label: 'Project' },
        {
          key: 'status',
          label: 'Status',
          render: (c) => (
            <span className="rounded-md bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-navy-800">
              {c.status}
            </span>
          ),
        },
        { key: 'lastContactDate', label: 'Last Contact' },
      ]}
      statusKey="status"
      statusOptions={CONTACT_STATUSES}
      fields={[
        { key: 'name', label: 'Name', type: 'text' },
        { key: 'title', label: 'Title', type: 'text' },
        { key: 'company', label: 'Company', type: 'text' },
        { key: 'category', label: 'Category', type: 'select', options: CONTACT_CATEGORIES },
        { key: 'email', label: 'Email', type: 'text' },
        { key: 'phone', label: 'Phone', type: 'text' },
        { key: 'projectName', label: 'Project', type: 'text' },
        { key: 'lastContactDate', label: 'Last contact date', type: 'date' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
      ]}
      itemTitle={(c) => c.name || 'New contact'}
      itemSubtitle={(c) => [c.title, c.company].filter(Boolean).join(' · ')}
      newRecord={() => ({
        name: 'New Contact',
        title: '',
        company: '',
        category: 'Other',
        email: '',
        phone: '',
        opportunityId: null,
        projectName: '',
        status: 'Active',
        lastContactDate: null,
        notes: '',
      })}
    />
  )
}
