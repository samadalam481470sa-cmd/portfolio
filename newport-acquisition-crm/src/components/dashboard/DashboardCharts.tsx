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
import type { AcquisitionStage, OpportunityStatus } from '@/types'

interface StatusDatum {
  status: OpportunityStatus | string
  count: number
}

interface StageDatum {
  stage: AcquisitionStage | string
  count: number
}

interface DashboardChartsProps {
  byStatus: StatusDatum[]
  byStage: StageDatum[]
}

const STATUS_COLORS: Record<string, string> = {
  Active: '#0b1f3a',
  Pending: '#3d7eb8',
  Inactive: '#8a93a3',
  Declined: '#c8ced8',
  Closed: '#5a6577',
  Completed: '#1f6b4a',
}

const STAGE_COLOR = '#3d7eb8'

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { value: number }[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-(--shadow-elevated)">
      <p className="font-semibold text-ink">{label}</p>
      <p className="mt-0.5 text-ink-muted">{payload[0].value} deal{payload[0].value === 1 ? '' : 's'}</p>
    </div>
  )
}

export function DashboardCharts({ byStatus, byStage }: DashboardChartsProps) {
  const stageData = byStage
    .filter((s) => s.count > 0)
    .map((s) => ({
      ...s,
      shortStage:
        s.stage.length > 14 ? `${String(s.stage).slice(0, 12)}…` : s.stage,
    }))

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
        <h2 className="font-brand text-lg font-bold text-navy-900">Deals by Status</h2>
        <p className="mt-0.5 mb-4 text-sm text-ink-muted">Distribution across opportunity status</p>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byStatus} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e6ed" vertical={false} />
              <XAxis
                dataKey="status"
                tick={{ fill: '#5a6577', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fill: '#8a93a3', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: '#e8f1f8' }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={40}>
                {byStatus.map((entry) => (
                  <Cell
                    key={entry.status}
                    fill={STATUS_COLORS[entry.status] ?? '#3d7eb8'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
        <h2 className="font-brand text-lg font-bold text-navy-900">Active Deals by Stage</h2>
        <p className="mt-0.5 mb-4 text-sm text-ink-muted">
          Where filtered opportunities sit in the acquisition process
        </p>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={stageData}
              layout="vertical"
              margin={{ top: 4, right: 16, left: 8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e6ed" horizontal={false} />
              <XAxis
                type="number"
                allowDecimals={false}
                tick={{ fill: '#8a93a3', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="shortStage"
                width={100}
                tick={{ fill: '#5a6577', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: '#e8f1f8' }} />
              <Bar dataKey="count" fill={STAGE_COLOR} radius={[0, 4, 4, 0]} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  )
}
