import { AlertTriangle, Briefcase, Clock, DollarSign, TrendingUp } from 'lucide-react'
import { KPICard } from './KPICard'
import { formatCurrency } from '@/utils/dashboard'
import type { DashboardFilters } from '@/types'

interface KPIRowProps {
  kpis: {
    activeDeals: number
    pendingDeals: number
    activeNwp: number
    activePfEbitda: number
    needsAttention: number
  }
  filters: DashboardFilters
  onStatusFilter: (status: DashboardFilters['status']) => void
}

export function KPIRow({ kpis, filters, onStatusFilter }: KPIRowProps) {
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
      <KPICard
        label="Active Deals"
        value={kpis.activeDeals}
        subtitle="In active pursuit"
        icon={<Briefcase className="h-4 w-4" strokeWidth={1.75} />}
        onClick={() => onStatusFilter('Active')}
        active={filters.status === 'Active'}
      />
      <KPICard
        label="Pending Deals"
        value={kpis.pendingDeals}
        subtitle="Awaiting progression"
        icon={<Clock className="h-4 w-4" strokeWidth={1.75} />}
        onClick={() => onStatusFilter('Pending')}
        active={filters.status === 'Pending'}
      />
      <KPICard
        label="Active NWP"
        value={formatCurrency(kpis.activeNwp)}
        subtitle="Net Written Premium"
        icon={<DollarSign className="h-4 w-4" strokeWidth={1.75} />}
      />
      <KPICard
        label="Active PF EBITDA"
        value={formatCurrency(kpis.activePfEbitda)}
        subtitle="Pro Forma EBITDA"
        icon={<TrendingUp className="h-4 w-4" strokeWidth={1.75} />}
      />
      <KPICard
        label="Needs Attention"
        value={kpis.needsAttention}
        subtitle="Overdue, stalled, or missing next steps"
        tone="attention"
        icon={<AlertTriangle className="h-4 w-4" strokeWidth={1.75} />}
        onClick={() => onStatusFilter('Needs Attention')}
        active={filters.status === 'Needs Attention'}
      />
    </div>
  )
}
