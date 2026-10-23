export type OpportunityStatus =
  | 'Active'
  | 'Pending'
  | 'Inactive'
  | 'Closed'
  | 'Declined'
  | 'Withdrew'
  | 'Completed'

export type AcquisitionStage =
  | 'Target Identified'
  | 'Initial Outreach'
  | 'Preliminary Discussion'
  | 'NDA'
  | 'Initial Review'
  | 'IOI / LOI'
  | 'Exclusivity'
  | 'Due Diligence'
  | 'Closing'

export type OpportunityType =
  | 'Platform Acquisition'
  | 'Add-on Acquisition'
  | 'Organic Growth Initiative'
  | 'Carrier Capacity'

export type SourceType =
  | 'Investment Banker'
  | 'Intermediary'
  | 'Direct MGA Relationship'
  | 'Carrier Partner'
  | 'Other'

export type TaskPriority = 'A' | 'B' | 'C'

export type AttentionReason =
  | 'Next action overdue'
  | 'No next action assigned'
  | 'No activity in 30+ days'
  | 'Upcoming deadline within 7 days'
  | 'No deal owner assigned'

export interface Opportunity {
  id: string
  projectNumber?: number
  projectName: string
  entityName: string
  type: OpportunityType
  status: OpportunityStatus
  stage: AcquisitionStage
  dealLead: string
  sourceType: SourceType
  sourceName: string
  specialty: string
  geography: string
  nwp: number
  netRevenue: number
  pfEbitda: number
  nextAction: string | null
  nextActionDate: string | null
  priority: TaskPriority
  lastActivityDate: string
  needsAttention: boolean
  attentionReasons: AttentionReason[]
  outstandingItems?: string[]
  diligenceNotes?: string
}

export interface PriorityTask {
  id: string
  priority: TaskPriority
  action: string
  projectId: string
  projectName: string
  owner: string
  dueDate: string
}

export interface ActivityItem {
  id: string
  actor: string | null
  message: string
  projectName: string
  timestamp: string
  type: 'stage_change' | 'note' | 'document' | 'status_change' | 'update'
}

export interface AttentionAlert {
  id: string
  reason: AttentionReason
  projectId: string
  projectName: string
  detail: string
}

export interface DashboardFilters {
  status: OpportunityStatus | 'All Deals' | 'Needs Attention'
  stage: AcquisitionStage | null
  search: string
}

export interface AuthUser {
  id: string
  email: string
  name: string
  role: string
  initials: string
}

export type OpportunityUpdate = Partial<
  Pick<
    Opportunity,
    | 'projectName'
    | 'entityName'
    | 'type'
    | 'status'
    | 'stage'
    | 'dealLead'
    | 'sourceType'
    | 'sourceName'
    | 'specialty'
    | 'geography'
    | 'nwp'
    | 'netRevenue'
    | 'pfEbitda'
    | 'nextAction'
    | 'nextActionDate'
    | 'priority'
    | 'needsAttention'
    | 'attentionReasons'
    | 'outstandingItems'
    | 'diligenceNotes'
  >
>
