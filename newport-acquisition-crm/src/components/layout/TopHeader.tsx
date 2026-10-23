import { Bell, Plus, Search } from 'lucide-react'
import { getGreeting } from '@/utils/dashboard'
import { useAuth } from '@/auth/AuthContext'

interface TopHeaderProps {
  search: string
  onSearchChange: (value: string) => void
  onNewOpportunity: () => void
}

export function TopHeader({ search, onSearchChange, onNewOpportunity }: TopHeaderProps) {
  const greeting = getGreeting()
  const { user } = useAuth()
  const firstName = user?.name.split(' ')[0] ?? 'there'
  const initials = user?.initials ?? 'NP'

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="flex flex-wrap items-start justify-between gap-4 px-6 py-5 lg:px-8">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold tracking-[0.14em] text-accent uppercase">
            Acquisition & Strategic Growth CRM
          </p>
          <h1 className="mt-1 font-brand text-2xl font-bold tracking-tight text-navy-900">
            {greeting}, {firstName}
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Snapshot of deal status, outstanding work, and diligence — one-stop acquisition
            tracking.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative">
            <Search
              className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-ink-subtle"
              strokeWidth={1.75}
            />
            <input
              type="search"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search projects, companies, contacts..."
              className="h-10 w-64 rounded-lg border border-border bg-canvas pr-3 pl-9 text-sm text-ink outline-none transition-shadow placeholder:text-ink-subtle focus:border-accent focus:ring-2 focus:ring-accent/20 lg:w-80"
              aria-label="Search opportunities"
            />
          </div>

          <button
            type="button"
            className="relative flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-surface text-ink-muted transition-colors hover:bg-canvas hover:text-ink"
            aria-label="Notifications"
          >
            <Bell className="h-4 w-4" strokeWidth={1.75} />
            <span className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-accent" />
          </button>

          <div
            className="flex h-10 w-10 items-center justify-center rounded-full bg-navy-900 text-xs font-semibold text-white"
            title={user?.name}
            aria-label={`Signed in as ${user?.name ?? 'user'}`}
          >
            {initials}
          </div>

          <button
            type="button"
            onClick={onNewOpportunity}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-navy-900 px-3.5 text-sm font-semibold text-white transition-colors hover:bg-navy-800"
          >
            <Plus className="h-4 w-4" strokeWidth={2} />
            New Opportunity
          </button>
        </div>
      </div>
    </header>
  )
}
