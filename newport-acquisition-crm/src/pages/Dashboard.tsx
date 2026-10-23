import { useMemo, useState, useCallback } from 'react'
import { TopHeader } from '@/components/layout/TopHeader'
import { StatusFilter } from '@/components/dashboard/StatusFilter'
import { KPIRow } from '@/components/dashboard/KPIRow'
import { PipelineOverview } from '@/components/dashboard/PipelineOverview'
import { PriorityDealsTable } from '@/components/dashboard/PriorityDealsTable'
import { PriorityTasks } from '@/components/dashboard/PriorityTasks'
import { AttentionAlerts } from '@/components/dashboard/AttentionAlerts'
import { DashboardCharts } from '@/components/dashboard/DashboardCharts'
import { RecentActivity } from '@/components/dashboard/RecentActivity'
import { QuickActions } from '@/components/dashboard/QuickActions'
import { NewportAI } from '@/components/dashboard/NewportAI'
import { OpportunityDrawer } from '@/components/dashboard/OpportunityDrawer'
import { mockActivity, mockAlerts, mockPriorityTasks } from '@/data/mockTasks'
import { DEMO_DISCLAIMER } from '@/data/constants'
import { useData } from '@/data/DataContext'
import type { AcquisitionStage, DashboardFilters, Opportunity } from '@/types'
import {
  computeDealsByStatus,
  computeKpis,
  computePipelineByStage,
  filterOpportunities,
  hasActiveFilters,
} from '@/utils/dashboard'

const DEFAULT_FILTERS: DashboardFilters = {
  status: 'All Deals',
  stage: null,
  search: '',
}

export function Dashboard() {
  const { opportunities } = useData()
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS)
  const [selected, setSelected] = useState<Opportunity | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const showToast = useCallback((message: string) => {
    setToast(message)
    window.setTimeout(() => setToast(null), 2800)
  }, [])

  const filtered = useMemo(
    () => filterOpportunities(opportunities, filters),
    [filters, opportunities],
  )

  /** Pipeline / KPIs use a broader set when status filter is active stages matter */
  const pipelineSource = useMemo(() => {
    // Pipeline should focus on Active + Pending for M&A view unless filtering Needs Attention
    if (filters.status === 'Needs Attention') {
      return opportunities.filter((o) => o.needsAttention)
    }
    if (filters.status === 'All Deals') {
      return opportunities.filter(
        (o) => o.status === 'Active' || o.status === 'Pending',
      )
    }
    return opportunities.filter((o) => o.status === filters.status)
  }, [filters.status, opportunities])

  const pipelineFiltered = useMemo(() => {
    if (!filters.search.trim()) return pipelineSource
    const q = filters.search.trim().toLowerCase()
    return pipelineSource.filter((o) =>
      `${o.projectName} ${o.entityName} ${o.dealLead}`.toLowerCase().includes(q),
    )
  }, [pipelineSource, filters.search])

  const kpis = useMemo(() => {
    // Executive KPIs always reflect full book unless searching
    const base = filters.search.trim()
      ? filterOpportunities(opportunities, {
          status: 'All Deals',
          stage: null,
          search: filters.search,
        })
      : opportunities
    return computeKpis(base)
  }, [filters.search, opportunities])

  const pipeline = useMemo(
    () => computePipelineByStage(pipelineFiltered),
    [pipelineFiltered],
  )

  const chartOpportunities = useMemo(() => {
    // Charts respond to status + search (not stage) so stage filter remains table-focused
    return filterOpportunities(opportunities, {
      status: filters.status,
      stage: null,
      search: filters.search,
    })
  }, [filters.status, filters.search, opportunities])

  const byStatus = useMemo(
    () => computeDealsByStatus(chartOpportunities),
    [chartOpportunities],
  )

  const byStage = useMemo(() => {
    const activeLike =
      filters.status === 'All Deals' || filters.status === 'Active'
        ? chartOpportunities.filter((o) => o.status === 'Active')
        : chartOpportunities
    return computePipelineByStage(activeLike).map(({ stage, count }) => ({
      stage,
      count,
    }))
  }, [chartOpportunities, filters.status])

  /** Priority table: show filtered set, prefer Active/Pending when viewing all */
  const tableRows = useMemo(() => {
    let rows = filtered
    if (filters.status === 'All Deals' && !filters.stage && !filters.search.trim()) {
      rows = opportunities.filter(
        (o) => o.status === 'Active' || o.status === 'Pending',
      )
    }
    return [...rows]
      .sort((a, b) => {
        const pri = { A: 0, B: 1, C: 2 }
        if (pri[a.priority] !== pri[b.priority]) return pri[a.priority] - pri[b.priority]
        if (a.needsAttention !== b.needsAttention) return a.needsAttention ? -1 : 1
        return a.projectName.localeCompare(b.projectName)
      })
      .slice(0, 8)
  }, [filtered, filters, opportunities])

  const setStatus = (status: DashboardFilters['status']) => {
    setFilters((prev) => ({
      ...prev,
      status: prev.status === status && status !== 'All Deals' ? 'All Deals' : status,
      // Clear stage when switching broad status chips for clarity
      stage: status === 'All Deals' ? prev.stage : null,
    }))
  }

  const setStage = (stage: AcquisitionStage | null) => {
    setFilters((prev) => ({ ...prev, stage }))
  }

  const clearFilters = () => setFilters(DEFAULT_FILTERS)

  const openById = (projectId: string) => {
    const opp = opportunities.find((o) => o.id === projectId) ?? null
    setSelected(opp)
  }

  return (
    <>
      <TopHeader
        search={filters.search}
        onSearchChange={(search) => setFilters((prev) => ({ ...prev, search }))}
        onNewOpportunity={() =>
          showToast('New Opportunity workflow — coming in a future sprint')
        }
      />

      <main className="flex-1 px-6 py-6 lg:px-8">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-5">
          <StatusFilter
            filters={filters}
            onStatusChange={setStatus}
            onClear={clearFilters}
            hasFilters={hasActiveFilters(filters)}
            resultCount={filtered.length}
          />

          <KPIRow kpis={kpis} filters={filters} onStatusFilter={setStatus} />

          <PipelineOverview
            stages={pipeline}
            selectedStage={filters.stage}
            onSelectStage={setStage}
          />

          <PriorityDealsTable opportunities={tableRows} onSelect={setSelected} />

          <div className="grid gap-4 lg:grid-cols-2">
            <PriorityTasks tasks={mockPriorityTasks} onProjectClick={openById} />
            <AttentionAlerts
              alerts={mockAlerts}
              onProjectClick={openById}
              onViewAll={() => setStatus('Needs Attention')}
            />
          </div>

          <DashboardCharts byStatus={byStatus} byStage={byStage} />

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-1">
              <RecentActivity items={mockActivity} />
            </div>
            <div className="flex flex-col gap-4 lg:col-span-2">
              <QuickActions
                onAction={(action) =>
                  showToast(
                    `${action.replace(/-/g, ' ')} — prototype action (no backend yet)`,
                  )
                }
              />
              <NewportAI />
            </div>
          </div>

          <p className="pb-4 text-center text-[11px] text-ink-subtle">{DEMO_DISCLAIMER}</p>
        </div>
      </main>

      <OpportunityDrawer opportunity={selected} onClose={() => setSelected(null)} />

      {toast && (
        <div
          role="status"
          className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-border bg-navy-900 px-4 py-2.5 text-sm text-white shadow-(--shadow-elevated)"
        >
          {toast}
        </div>
      )}
    </>
  )
}
