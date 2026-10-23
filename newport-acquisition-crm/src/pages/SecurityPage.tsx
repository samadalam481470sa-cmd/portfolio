import { useEffect, useState } from 'react'
import {
  fetchApiKeySlots,
  fetchAuditLogs,
  fetchChangeHistory,
  getStoredSession,
  type ChangeHistoryEntry,
} from '@/lib/api'
import { loadDemoChangeHistory } from '@/lib/demoStore'
import { History, KeyRound, ScrollText, Shield } from 'lucide-react'

const DEMO_SLOTS = [
  { slot: 1, label: 'Primary integration (demo)', key_prefix: 'nwp_demo_', status: 'active', last_used_at: null },
  { slot: 2, label: 'Reserved slot 2', key_prefix: 'nwp_slot2_', status: 'pending', last_used_at: null },
  { slot: 3, label: 'Reserved slot 3', key_prefix: 'nwp_slot3_', status: 'pending', last_used_at: null },
  { slot: 4, label: 'Reserved slot 4', key_prefix: 'nwp_slot4_', status: 'pending', last_used_at: null },
  { slot: 5, label: 'Reserved slot 5', key_prefix: 'nwp_slot5_', status: 'pending', last_used_at: null },
]

export function SecurityPage() {
  const [slots, setSlots] = useState<
    Array<{
      slot: number
      label: string
      key_prefix: string
      status: string
      last_used_at: string | null
    }>
  >([])
  const [logs, setLogs] = useState<
    Array<{
      id: string
      actor_name: string | null
      action: string
      detail: string
      created_at: string
    }>
  >([])
  const [changes, setChanges] = useState<ChangeHistoryEntry[]>([])
  const [slotFilter, setSlotFilter] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      if (getStoredSession()?.token === 'local-demo') {
        setSlots(DEMO_SLOTS)
        setLogs([])
        const local = loadDemoChangeHistory().map((c, i) => ({
          id: `local_${i}_${c.createdAt}`,
          actorName: c.actorName,
          apiKeySlot: null,
          authMethod: 'demo',
          resourceType: c.resourceType,
          resourceId: c.resourceId,
          changeType: c.changeType,
          changedFields: c.changedFields,
          before: null,
          after: null,
          createdAt: c.createdAt,
        }))
        setChanges(local.slice(0, 80))
        setError(null)
        return
      }
      try {
        const [keys, audit, history] = await Promise.all([
          fetchApiKeySlots(),
          fetchAuditLogs(30),
          fetchChangeHistory({ limit: 80, slot: slotFilter }),
        ])
        setSlots(keys.slots)
        setLogs(audit)
        setChanges(history.changes)
        setError(null)
      } catch (err) {
        setSlots(DEMO_SLOTS)
        setLogs([])
        setChanges(
          loadDemoChangeHistory().map((c, i) => ({
            id: `local_${i}_${c.createdAt}`,
            actorName: c.actorName,
            apiKeySlot: null,
            authMethod: 'demo',
            resourceType: c.resourceType,
            resourceId: c.resourceId,
            changeType: c.changeType,
            changedFields: c.changedFields,
            before: null,
            after: null,
            createdAt: c.createdAt,
          })),
        )
        setError(err instanceof Error ? err.message : 'Failed to load security data')
      }
    })()
  }, [slotFilter])

  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-border bg-surface px-6 py-5 lg:px-8">
        <h1 className="font-brand text-2xl font-bold text-navy-900">Security</h1>
        <p className="mt-1 text-sm text-ink-muted">
          API key infrastructure (5 slots), permanent change history for every daily edit, and
          access controls. Keys are provisioned by the security team — this app only stores hashes.
        </p>
      </header>

      <div className="mx-auto grid w-full max-w-[1200px] gap-5 px-6 py-6 lg:grid-cols-2 lg:px-8">
        {error && (
          <p className="lg:col-span-2 rounded-lg border border-attention-border bg-attention-bg px-3 py-2 text-sm text-attention">
            {error}
          </p>
        )}

        <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
          <div className="mb-4 flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-accent" />
            <h2 className="font-brand text-lg font-bold text-navy-900">API key slots (5)</h2>
          </div>
          <ul className="space-y-2">
            {slots.map((slot) => (
              <li
                key={slot.slot}
                className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5"
              >
                <div>
                  <p className="text-sm font-semibold text-ink">
                    Slot {slot.slot} — {slot.label}
                  </p>
                  <p className="text-xs text-ink-subtle">
                    Prefix {slot.key_prefix}… ·{' '}
                    {slot.last_used_at ? `Last used ${slot.last_used_at}` : 'Never used'}
                  </p>
                </div>
                <span
                  className={`rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase ${
                    slot.status === 'active'
                      ? 'bg-success-bg text-success'
                      : slot.status === 'pending'
                        ? 'bg-warning-bg text-warning'
                        : 'bg-canvas text-ink-muted'
                  }`}
                >
                  {slot.status}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-ink-subtle">
            Security team will issue the five production keys. Demo key exists only for slot 1 in
            local environments.
          </p>
        </section>

        <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card)">
          <div className="mb-4 flex items-center gap-2">
            <Shield className="h-5 w-5 text-accent" />
            <h2 className="font-brand text-lg font-bold text-navy-900">Controls in place</h2>
          </div>
          <ul className="space-y-2 text-sm text-ink">
            <li>• Auth required for all CRM data routes</li>
            <li>• API keys hashed (SHA-256); plaintext never stored</li>
            <li>• Session tokens hashed; 8–12 hour expiry</li>
            <li>• Brute-force lockout after 5 failed attempts</li>
            <li>• Role checks (admin / partner / analyst / viewer)</li>
            <li>• Rate limiting on auth and API</li>
            <li>• Helmet security headers + CSP</li>
            <li>• Permanent change history with before/after snapshots</li>
            <li>• Audit log for sign-in and every write</li>
          </ul>
        </section>

        <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card) lg:col-span-2">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-accent" />
              <h2 className="font-brand text-lg font-bold text-navy-900">
                Change history (all 5 keys)
              </h2>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setSlotFilter(null)}
                className={`rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase ${
                  slotFilter === null
                    ? 'bg-navy-900 text-white'
                    : 'border border-border bg-canvas text-ink-muted'
                }`}
              >
                All
              </button>
              {[1, 2, 3, 4, 5].map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSlotFilter(s)}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase ${
                    slotFilter === s
                      ? 'bg-navy-900 text-white'
                      : 'border border-border bg-canvas text-ink-muted'
                  }`}
                >
                  Slot {s}
                </button>
              ))}
            </div>
          </div>
          <p className="mb-3 text-xs text-ink-muted">
            Every create, update, and delete is saved permanently with before/after values and
            attributed to the API key slot (or demo session) that made it — so daily deal edits are
            never lost.
          </p>
          <ul className="divide-y divide-border">
            {changes.length === 0 && (
              <li className="py-3 text-sm text-ink-muted">
                No changes recorded yet{slotFilter ? ` for slot ${slotFilter}` : ''}.
              </li>
            )}
            {changes.map((chg) => (
              <li key={chg.id} className="py-2.5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-sm font-medium text-ink">
                    <span className="font-semibold">{chg.actorName ?? 'System'}</span>
                    {chg.apiKeySlot ? (
                      <span className="ml-1.5 rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent uppercase">
                        Key slot {chg.apiKeySlot}
                      </span>
                    ) : (
                      <span className="ml-1.5 rounded bg-canvas px-1.5 py-0.5 text-[10px] font-semibold text-ink-subtle uppercase">
                        {chg.authMethod}
                      </span>
                    )}{' '}
                    — {chg.changeType} {chg.resourceType}
                    <span className="text-ink-muted"> · {chg.resourceId}</span>
                  </p>
                  <span className="text-[11px] text-ink-subtle">{chg.createdAt}</span>
                </div>
                {chg.changedFields.length > 0 && (
                  <p className="mt-0.5 text-xs text-ink-muted">
                    Fields: {chg.changedFields.slice(0, 12).join(', ')}
                    {chg.changedFields.length > 12 ? '…' : ''}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-xl border border-border bg-surface p-5 shadow-(--shadow-card) lg:col-span-2">
          <div className="mb-4 flex items-center gap-2">
            <ScrollText className="h-5 w-5 text-accent" />
            <h2 className="font-brand text-lg font-bold text-navy-900">Recent audit activity</h2>
          </div>
          <ul className="divide-y divide-border">
            {logs.length === 0 && (
              <li className="py-3 text-sm text-ink-muted">No audit events yet.</li>
            )}
            {logs.map((log) => (
              <li key={log.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2.5">
                <div>
                  <p className="text-sm font-medium text-ink">
                    <span className="font-semibold">{log.actor_name ?? 'System'}</span> —{' '}
                    {log.action}
                  </p>
                  <p className="text-xs text-ink-muted">{log.detail}</p>
                </div>
                <span className="text-[11px] text-ink-subtle">{log.created_at}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
