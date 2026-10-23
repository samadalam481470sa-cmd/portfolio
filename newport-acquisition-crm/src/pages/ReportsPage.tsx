import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Download, FileJson, DatabaseBackup } from 'lucide-react'
import { useData } from '@/data/DataContext'
import { useResource } from '@/hooks/useResource'
import { mockPortfolio, type PortfolioRecord } from '@/data/mockModules'
import { SOURCE_TYPES } from '@/data/constants'
import {
  computeDealsByStatus,
  computePipelineByStage,
  formatCurrency,
} from '@/utils/dashboard'
import {
  downloadDatabaseFile,
  downloadOpportunitiesCsv,
  downloadOpportunitiesJson,
} from '@/lib/api'

const NAVY = '#0b1f3a'
const ACCENT = '#3d7eb8'

function ReportTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { value: number; name?: string }[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-(--shadow-elevated)">
      <p className="font-semibold text-ink">{label}</p>
      <p className="mt-0.5 text-ink-muted">{payload[0].value}</p>
    </div>
  )
}

export function ReportsPage() {
  const { opportunities } = useData()
  const portfolio = useResource<PortfolioRecord>('portfolio', mockPortfolio)
  const [exportMsg, setExportMsg] = useState<string | null>(null)

  const active = useMemo(
    () => opportunities.filter((o) => o.status === 'Active'),
    [opportunities],
  )

  const byStatus = useMemo(() => computeDealsByStatus(opportunities), [opportunities])
  const byStage = useMemo(
    () =>
      computePipelineByStage(active)
        .filter((s) => s.count > 0)
        .map((s) => ({ ...s, shortStage: s.stage.length > 14 ? `${s.stage.slice(0, 12)}…` : s.stage })),
    [active],
  )

  const bySource = useMemo(
    () =>
      SOURCE_TYPES.map((type) => ({
        type,
        nwp: Math.round(
          opportunities
            .filter((o) => o.sourceType === type && (o.status === 'Active' || o.status === 'Pending'))
            .reduce((sum, o) => sum + o.nwp, 0) / 1_000_000,
        ),
      })).filter((s) => s.nwp > 0),
    [opportunities],
  )

  const byLead = useMemo(() => {
    const counts = new Map<string, number>()
    for (const o of opportunities) {
      if (o.status !== 'Active' && o.status !== 'Pending') continue
      const lead = o.dealLead || 'Unassigned'
      counts.set(lead, (counts.get(lead) ?? 0) + 1)
    }
    return [...counts.entries()].map(([lead, count]) => ({ lead, count }))
  }, [opportunities])

  const totals = useMemo(
    () => ({
      activeDeals: active.length,
      activeNwp: active.reduce((s, o) => s + o.nwp, 0),
      activeEbitda: active.reduce((s, o) => s + o.pfEbitda, 0),
      portfolioCount: portfolio.items.length,
      portfolioNwp: portfolio.items.reduce((s, p) => s + p.nwp, 0),
    }),
    [active, portfolio.items],
  )

  const runExport = async (fn: () => Promise<void>, label: string) => {
    setExportMsg(null)
    try {
      await fn()
      setExportMsg(`${label} downloaded`)
    } catch {
      setExportMsg(`${label} requires the database server (run npm run dev locally)`)
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border bg-surface px-6 py-5 lg:px-8">
        <div>
          <h1 className="font-brand text-2xl font-bold text-navy-900">Reports</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Pipeline analytics and database exports for partner reviews.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void runExport(downloadOpportunitiesCsv, 'CSV')}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-ink hover:bg-accent-soft"
          >
            <Download className="h-4 w-4 text-accent" /> CSV (Excel)
          </button>
          <button
            type="button"
            onClick={() => void runExport(downloadOpportunitiesJson, 'JSON')}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-ink hover:bg-accent-soft"
          >
            <FileJson className="h-4 w-4 text-accent" /> JSON
          </button>
          <button
            type="button"
            onClick={() => void runExport(downloadDatabaseFile, 'Database file')}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-navy-900 px-3 text-sm font-semibold text-white hover:bg-navy-800"
          >
            <DatabaseBackup className="h-4 w-4" /> Full database
          </button>
        </div>
      </header>

      {exportMsg && (
        <p className="border-b border-border bg-accent-soft/50 px-6 py-2 text-sm text-navy-800 lg:px-8">
          {exportMsg}
        </p>
      )}

      <div className="mx-auto w-full max-w-[1400px] space-y-5 px-6 py-6 lg:px-8">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {[
            { label: 'Active Deals', value: String(totals.activeDeals) },
            { label: 'Active NWP', value: formatCurrency(totals.activeNwp) },
            { label: 'Active PF EBITDA', value: formatCurrency(totals.activeEbitda) },
            { label: 'Portfolio Companies', value: String(totals.portfolioCount) },
            { label: 'Portfolio NWP', value: formatCurrency(totals.portfolioNwp) },
          ].map((kpi) => (
            <div
              key={kpi.label}
              className="rounded-xl border border-border bg-surface p-4 shadow-(--shadow-card)"
            >
              <p className="text-[11px] font-semibold tracking-[0.08em] text-ink-muted uppercase">
                {kpi.label}
              </p>
              <p className="mt-2 font-brand text-2xl font-bold text-navy-900">{kpi.value}</p>
            </div>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
            <h2 className="mb-4 font-brand text-lg font-bold text-navy-900">Deals by Status</h2>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byStatus} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e6ed" vertical={false} />
                  <XAxis dataKey="status" tick={{ fill: '#5a6577', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: '#8a93a3', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ReportTooltip />} cursor={{ fill: '#e8f1f8' }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={40}>
                    {byStatus.map((entry, i) => (
                      <Cell key={entry.status} fill={i % 2 === 0 ? NAVY : ACCENT} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
            <h2 className="mb-4 font-brand text-lg font-bold text-navy-900">
              Active Deals by Stage
            </h2>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byStage} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e6ed" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} tick={{ fill: '#8a93a3', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="shortStage" width={100} tick={{ fill: '#5a6577', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ReportTooltip />} cursor={{ fill: '#e8f1f8' }} />
                  <Bar dataKey="count" fill={ACCENT} radius={[0, 4, 4, 0]} maxBarSize={22} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
            <h2 className="mb-4 font-brand text-lg font-bold text-navy-900">
              Pipeline NWP by Source Type ($M)
            </h2>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bySource} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e6ed" vertical={false} />
                  <XAxis dataKey="type" tick={{ fill: '#5a6577', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#8a93a3', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ReportTooltip />} cursor={{ fill: '#e8f1f8' }} />
                  <Bar dataKey="nwp" fill={NAVY} radius={[4, 4, 0, 0]} maxBarSize={40} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
            <h2 className="mb-4 font-brand text-lg font-bold text-navy-900">
              Pipeline Deals by Lead
            </h2>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byLead} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e6ed" vertical={false} />
                  <XAxis dataKey="lead" tick={{ fill: '#5a6577', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: '#8a93a3', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ReportTooltip />} cursor={{ fill: '#e8f1f8' }} />
                  <Bar dataKey="count" fill={ACCENT} radius={[4, 4, 0, 0]} maxBarSize={40} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
