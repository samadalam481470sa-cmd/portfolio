import type { ReactNode } from 'react'

interface KPICardProps {
  label: string
  value: string | number
  subtitle?: string
  tone?: 'default' | 'attention'
  onClick?: () => void
  active?: boolean
  icon?: ReactNode
}

export function KPICard({
  label,
  value,
  subtitle,
  tone = 'default',
  onClick,
  active,
  icon,
}: KPICardProps) {
  const isAttention = tone === 'attention'
  const interactive = Boolean(onClick)

  const base =
    'relative flex flex-col rounded-xl border bg-surface p-4 shadow-(--shadow-card) transition-all'
  const toneClass = isAttention
    ? 'border-attention-border bg-attention-bg'
    : 'border-border'
  const activeClass = active
    ? isAttention
      ? 'ring-2 ring-attention/30 border-attention'
      : 'ring-2 ring-accent/30 border-accent'
    : ''
  const hoverClass = interactive
    ? 'cursor-pointer hover:shadow-(--shadow-elevated) hover:-translate-y-0.5'
    : ''

  const content = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p
          className={`text-[11px] font-semibold tracking-[0.08em] uppercase ${
            isAttention ? 'text-attention' : 'text-ink-muted'
          }`}
        >
          {label}
        </p>
        {icon && (
          <span className={isAttention ? 'text-attention/70' : 'text-accent/70'}>{icon}</span>
        )}
      </div>
      <p className="mt-2 font-brand text-3xl font-bold tracking-tight text-navy-900">{value}</p>
      {subtitle && <p className="mt-1 text-xs text-ink-subtle">{subtitle}</p>}
    </>
  )

  if (interactive) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${base} ${toneClass} ${activeClass} ${hoverClass} text-left`}
      >
        {content}
      </button>
    )
  }

  return <div className={`${base} ${toneClass}`}>{content}</div>
}
