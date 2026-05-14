import type { FindingSummary } from '@/lib/types'
import { SeverityPill } from '@/components/SeverityPill'
import { countryFlag, currencyCode, fmtAmount, fmtHours } from '@/lib/format'

interface Props {
  finding: FindingSummary
  selected: boolean
  onClick: () => void
}

export function FindingCard({ finding, selected, onClick }: Props) {
  const countries = finding.countries ?? []
  const banks = finding.banks ?? []
  const ccy = currencyCode(finding.currency)
  return (
    <button
      onClick={onClick}
      className={`glass group flex w-full flex-col gap-3 rounded-xl px-4 py-3 text-left transition-all hover:translate-y-[-1px] hover:border-[var(--color-border-strong)] ${
        selected
          ? 'border-[var(--color-accent)]/70 !bg-[rgba(192,132,252,0.07)] shadow-[0_0_0_1px_rgba(192,132,252,0.4),0_8px_32px_rgba(192,132,252,0.08)]'
          : ''
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <SeverityPill severity={finding.severity} size="sm" />
          <span className="text-[10px] font-medium uppercase tracking-widest text-[var(--color-fg-dim)]">
            {finding.finding_type.replace(/_/g, ' ')}
          </span>
        </div>
        <span className="mono text-[10px] text-[var(--color-fg-dim)]">#{finding.finding_id}</span>
      </div>

      <div className="flex items-baseline gap-2">
        <span className="text-lg font-semibold tabular-nums text-[var(--color-fg)]">
          {fmtAmount(finding.amount_max, null)}
        </span>
        <span className="text-xs text-[var(--color-fg-muted)]">
          {ccy} · {fmtHours(finding.time_span_hours)} span
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        {countries.map((c) => (
          <span
            key={c}
            className="inline-flex items-center gap-1 rounded-md bg-white/[0.04] px-1.5 py-0.5 text-[var(--color-fg)] ring-1 ring-inset ring-[var(--color-border)]"
          >
            <span>{countryFlag(c)}</span>
            <span className="mono">{c}</span>
          </span>
        ))}
        <span className="text-[var(--color-fg-dim)]">·</span>
        <span className="text-[var(--color-fg-muted)]">
          {finding.bank_count ?? 0} banks · {finding.party_count ?? 0} parties
        </span>
      </div>

      <div className="flex items-center justify-between">
        <span className="truncate text-[10px] text-[var(--color-fg-dim)]">
          {banks.join(' · ')}
        </span>
        <svg
          className={`transition-all ${
            selected
              ? 'translate-x-0 text-[var(--color-accent)]'
              : '-translate-x-1 text-[var(--color-fg-dim)] opacity-0 group-hover:translate-x-0 group-hover:opacity-100'
          }`}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
        >
          <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </button>
  )
}
