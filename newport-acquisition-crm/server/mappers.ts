import type { Opportunity, OpportunityStatus, AcquisitionStage, OpportunityType, SourceType, TaskPriority, AttentionReason } from '../../src/types/index.ts'

export interface DbOpportunityRow {
  id: string
  project_number: number
  project_name: string
  entity_name: string
  type: string
  status: string
  stage: string
  deal_lead: string
  source_type: string
  source_name: string
  specialty: string
  geography: string
  nwp: number
  net_revenue: number
  pf_ebitda: number
  next_action: string | null
  next_action_date: string | null
  priority: string
  last_activity_date: string
  needs_attention: number
  attention_reasons: string
  outstanding_items: string
  diligence_notes: string
  created_at?: string
  updated_at?: string
}

export interface ApiOpportunity extends Opportunity {
  projectNumber: number
  outstandingItems: string[]
  diligenceNotes: string
}

export function rowToOpportunity(row: DbOpportunityRow): ApiOpportunity {
  return {
    id: row.id,
    projectNumber: row.project_number,
    projectName: row.project_name,
    entityName: row.entity_name,
    type: row.type as OpportunityType,
    status: row.status as OpportunityStatus,
    stage: row.stage as AcquisitionStage,
    dealLead: row.deal_lead,
    sourceType: row.source_type as SourceType,
    sourceName: row.source_name,
    specialty: row.specialty,
    geography: row.geography,
    nwp: row.nwp,
    netRevenue: row.net_revenue,
    pfEbitda: row.pf_ebitda,
    nextAction: row.next_action,
    nextActionDate: row.next_action_date,
    priority: row.priority as TaskPriority,
    lastActivityDate: row.last_activity_date,
    needsAttention: Boolean(row.needs_attention),
    attentionReasons: JSON.parse(row.attention_reasons || '[]') as AttentionReason[],
    outstandingItems: JSON.parse(row.outstanding_items || '[]') as string[],
    diligenceNotes: row.diligence_notes || '',
  }
}
