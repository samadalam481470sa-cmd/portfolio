import { describe, it, expect } from 'vitest'
import {
  computeKpis,
  filterOpportunities,
  hasActiveFilters,
} from '@/utils/dashboard'
import { mockOpportunities } from '@/data/mockOpportunities'
import type { DashboardFilters } from '@/types'

describe('dashboard filters', () => {
  it('filters by Active status', () => {
    const filters: DashboardFilters = {
      status: 'Active',
      stage: null,
      search: '',
    }
    const result = filterOpportunities(mockOpportunities, filters)
    expect(result.every((o) => o.status === 'Active')).toBe(true)
    expect(result.length).toBeGreaterThan(0)
  })

  it('filters by stage', () => {
    const filters: DashboardFilters = {
      status: 'All Deals',
      stage: 'NDA',
      search: '',
    }
    const result = filterOpportunities(mockOpportunities, filters)
    expect(result.every((o) => o.stage === 'NDA')).toBe(true)
  })

  it('filters by search on project and entity', () => {
    const filters: DashboardFilters = {
      status: 'All Deals',
      stage: null,
      search: 'guardian',
    }
    const result = filterOpportunities(mockOpportunities, filters)
    expect(result).toHaveLength(1)
    expect(result[0].projectName).toBe('Project Guardian')
  })

  it('filters needs attention', () => {
    const filters: DashboardFilters = {
      status: 'Needs Attention',
      stage: null,
      search: '',
    }
    const result = filterOpportunities(mockOpportunities, filters)
    expect(result.every((o) => o.needsAttention)).toBe(true)
  })

  it('computes KPIs from data rather than hard-coded values', () => {
    const kpis = computeKpis(mockOpportunities)
    const active = mockOpportunities.filter((o) => o.status === 'Active')
    expect(kpis.activeDeals).toBe(active.length)
    expect(kpis.activeNwp).toBe(active.reduce((s, o) => s + o.nwp, 0))
  })

  it('detects active filters', () => {
    expect(
      hasActiveFilters({ status: 'All Deals', stage: null, search: '' }),
    ).toBe(false)
    expect(
      hasActiveFilters({ status: 'Active', stage: null, search: '' }),
    ).toBe(true)
  })
})
