import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { KeyRound, ShieldCheck, Lock, Fingerprint, FileClock, Timer } from 'lucide-react'
import { useAuth } from '@/auth/AuthContext'
import newportLogo from '@/assets/newport-logo.png'

export function LoginPage() {
  const { isAuthenticated, signInDemo, signInWithApiKey } = useAuth()
  const navigate = useNavigate()
  const [apiKey, setApiKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (isAuthenticated) return <Navigate to="/" replace />

  const onDemo = async () => {
    setBusy(true)
    setError(null)
    try {
      await signInDemo()
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  const onApiKey = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signInWithApiKey(apiKey.trim())
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'API key rejected')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-gradient-to-br from-navy-950 via-navy-900 to-navy-800 px-4 py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(61,126,184,0.18),_transparent_55%)]" />

      <div className="relative w-full max-w-md overflow-hidden rounded-2xl border border-white/10 bg-surface shadow-(--shadow-elevated)">
        {/* Brand banner */}
        <div className="border-b border-border">
          <img
            src={newportLogo}
            alt="Newport Specialty Partners"
            className="h-32 w-full object-cover object-center"
          />
        </div>

        <div className="p-8">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h1 className="font-brand text-xl font-bold tracking-tight text-navy-900">
                Secure Sign-In
              </h1>
              <p className="mt-1 text-xs tracking-[0.1em] text-ink-muted uppercase">
                Acquisition Management Platform
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-canvas px-2.5 py-1 text-[10px] font-semibold tracking-wide text-ink-muted uppercase">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Encrypted
            </span>
          </div>

          <p className="mt-3 text-sm leading-relaxed text-ink-muted">
            This system contains confidential acquisition data. Access is restricted to
            authorized Newport Specialty Partners personnel and monitored at all times.
          </p>

          <button
            type="button"
            disabled={busy}
            onClick={() => void onDemo()}
            className="mt-6 flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-navy-900 text-sm font-semibold text-white transition-colors hover:bg-navy-800 disabled:opacity-60"
          >
            <ShieldCheck className="h-4 w-4" strokeWidth={1.75} />
            Sign in — Demo access
          </button>
          <p className="mt-2 text-center text-[11px] text-ink-subtle">
            Production sign-in will require a provisioned credential.
          </p>

          <div className="my-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-border" />
            <span className="text-[11px] tracking-wide text-ink-subtle uppercase">
              Partner API key
            </span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <form onSubmit={(e) => void onApiKey(e)} className="space-y-3">
            <div className="flex items-baseline justify-between">
              <label
                htmlFor="api-key"
                className="block text-xs font-semibold tracking-[0.06em] text-ink-muted uppercase"
              >
                Enterprise API key
              </label>
              <span className="text-[10px] text-ink-subtle">5 provisioned slots</span>
            </div>
            <div className="relative">
              <KeyRound className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-ink-subtle" />
              <input
                id="api-key"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="nwp_ ••••••••••••••••"
                className="h-11 w-full rounded-xl border border-border bg-canvas pr-3 pl-10 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
              />
            </div>
            <button
              type="submit"
              disabled={busy || apiKey.trim().length < 16}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-xl border border-border bg-canvas text-sm font-semibold text-ink transition-colors hover:bg-accent-soft disabled:opacity-50"
            >
              <Lock className="h-4 w-4" strokeWidth={1.75} />
              Authenticate
            </button>
            <p className="text-[11px] leading-relaxed text-ink-subtle">
              Keys are issued and rotated exclusively by the Newport Information Security
              team. Lost or compromised keys must be reported immediately for revocation.
            </p>
          </form>

          {error && (
            <p className="mt-4 rounded-lg border border-attention-border bg-attention-bg px-3 py-2 text-sm text-attention">
              {error}
            </p>
          )}

          <div className="mt-7 grid grid-cols-3 gap-2 border-t border-border pt-5">
            <div className="flex flex-col items-center gap-1.5 text-center">
              <Fingerprint className="h-4 w-4 text-accent" strokeWidth={1.75} />
              <span className="text-[10px] leading-tight text-ink-subtle">
                SHA-256 hashed credentials
              </span>
            </div>
            <div className="flex flex-col items-center gap-1.5 text-center">
              <FileClock className="h-4 w-4 text-accent" strokeWidth={1.75} />
              <span className="text-[10px] leading-tight text-ink-subtle">
                Full audit trail on every action
              </span>
            </div>
            <div className="flex flex-col items-center gap-1.5 text-center">
              <Timer className="h-4 w-4 text-accent" strokeWidth={1.75} />
              <span className="text-[10px] leading-tight text-ink-subtle">
                Auto-expiring sessions
              </span>
            </div>
          </div>
        </div>
      </div>

      <p className="relative mt-6 max-w-md text-center text-[11px] leading-relaxed text-white/50">
        © 2026 Newport Specialty Partners. Authorized users only. Unauthorized access is
        prohibited and all activity is logged, monitored, and subject to review.
      </p>
    </div>
  )
}
