import type {
  AcquisitionStage,
  DashboardFilters,
  Opportunity,
  OpportunityStatus,
} from '@/types'
import { ACQUISITION_STAGES } from '@/data/constants'

export function formatCurrency(value: number, compact = true): string {
  if (compact) {
    if (value >= 1_000_000_000) {
      return `$${(value / 1_000_000_000).toFixed(1)}B`
    }
    if (value >= 1_000_000) {
      const millions = value / 1_000_000
      return millions >= 100
        ? `$${Math.round(millions)}M`
        : `$${millions % 1 === 0 ? millions.toFixed(0) : millions.toFixed(1)}M`
    }
    if (value >= 1_000) {
      return `$${Math.round(value / 1_000)}K`
    }
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  const date = new Date(dateStr.includes('T') ? dateStr : `${dateStr}T12:00:00`)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function formatRelativeTime(iso: string, now = new Date()): string {
  const then = new Date(iso)
  const diffMs = now.getTime() - then.getTime()
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffHours / 24)

  if (diffHours < 1) return 'Just now'
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  return formatDate(iso)
}

export function getGreeting(hour = new Date().getHours()): string {
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export function filterOpportunities(
  opportunities: Opportunity[],
  filters: DashboardFilters,
): Opportunity[] {
  return opportunities.filter((opp) => {
    if (filters.status === 'Needs Attention') {
      if (!opp.needsAttention) return false
    } else if (filters.status !== 'All Deals') {
      if (opp.status !== filters.status) return false
    }

    if (filters.stage && opp.stage !== filters.stage) return false

    if (filters.search.trim()) {
      const q = filters.search.trim().toLowerCase()
      const haystack = `${opp.projectName} ${opp.entityName} ${opp.dealLead}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }

    return true
  })
}

export function computeKpis(opportunities: Opportunity[]) {
  const active = opportunities.filter((o) => o.status === 'Active')
  const pending = opportunities.filter((o) => o.status === 'Pending')
  const needsAttention = opportunities.filter((o) => o.needsAttention)

  return {
    activeDeals: active.length,
    pendingDeals: pending.length,
    activeNwp: active.reduce((sum, o) => sum + o.nwp, 0),
    activePfEbitda: active.reduce((sum, o) => sum + o.pfEbitda, 0),
    needsAttention: needsAttention.length,
  }
}

export function computePipelineByStage(
  opportunities: Opportunity[],
  stages: readonly AcquisitionStage[] = ACQUISITION_STAGES,
) {
  return stages.map((stage) => {
    const deals = opportunities.filter((o) => o.stage === stage)
    return {
      stage,
      count: deals.length,
      nwp: deals.reduce((sum, o) => sum + o.nwp, 0),
    }
  })
}

export function computeDealsByStatus(opportunities: Opportunity[]) {
  const statuses: OpportunityStatus[] = [
    'Active',
    'Pending',
    'Inactive',
    'Declined',
    'Closed',
    'Completed',
  ]
  return statuses.map((status) => ({
    status,
    count: opportunities.filter((o) => o.status === status).length,
  }))
}

export function hasActiveFilters(filters: DashboardFilters): boolean {
  return (
    filters.status !== 'All Deals' ||
    filters.stage !== null ||
    filters.search.trim().length > 0
  )
}
