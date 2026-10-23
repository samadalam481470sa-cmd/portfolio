import { useResource } from '@/hooks/useResource'
import { ResourceWorkspace } from '@/components/shared/ResourceWorkspace'
import {
  CONFIDENTIALITY_LEVELS,
  DOCUMENT_STATUSES,
  DOCUMENT_TYPES,
  mockDocuments,
  type DocumentRecord,
} from '@/data/mockModules'

export function DocumentsPage() {
  const api = useResource<DocumentRecord>('documents', mockDocuments)

  return (
    <ResourceWorkspace<DocumentRecord>
      title="Documents"
      description="Deal document register — NDAs, LOIs, financials, and diligence reports."
      api={api}
      searchKeys={['name', 'projectName', 'docType', 'uploadedBy']}
      columns={[
        { key: 'name', label: 'Document' },
        { key: 'docType', label: 'Type' },
        { key: 'projectName', label: 'Project' },
        {
          key: 'status',
          label: 'Status',
          render: (d) => (
            <span
              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                d.status === 'Executed'
                  ? 'bg-success-bg text-success'
                  : d.status === 'In Review'
                    ? 'bg-accent-soft text-navy-800'
                    : 'bg-canvas text-ink-muted'
              }`}
            >
              {d.status}
            </span>
          ),
        },
        { key: 'confidentiality', label: 'Confidentiality' },
        { key: 'uploadedAt', label: 'Uploaded' },
      ]}
      statusKey="status"
      statusOptions={DOCUMENT_STATUSES}
      fields={[
        { key: 'name', label: 'Document name', type: 'text' },
        { key: 'docType', label: 'Type', type: 'select', options: DOCUMENT_TYPES },
        { key: 'projectName', label: 'Project', type: 'text' },
        {
          key: 'confidentiality',
          label: 'Confidentiality',
          type: 'select',
          options: CONFIDENTIALITY_LEVELS,
        },
        { key: 'uploadedBy', label: 'Uploaded by', type: 'text' },
        { key: 'uploadedAt', label: 'Uploaded date', type: 'date' },
        { key: 'link', label: 'Secure link (data room URL)', type: 'text', placeholder: 'https://…' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
      ]}
      itemTitle={(d) => d.name || 'New document'}
      itemSubtitle={(d) => [d.docType, d.projectName].filter(Boolean).join(' · ')}
      newRecord={() => ({
        name: 'New Document',
        docType: 'Other',
        opportunityId: null,
        projectName: '',
        status: 'Draft',
        confidentiality: 'Confidential',
        uploadedBy: '',
        link: '',
        uploadedAt: new Date().toISOString().slice(0, 10),
        notes: '',
      })}
    />
  )
}
