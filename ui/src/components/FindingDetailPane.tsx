import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { FindingDetail, FindingGraph } from '@/lib/types'
import { SeverityPill } from '@/components/SeverityPill'
import { RingGraph } from '@/components/RingGraph'
import {
  countryFlag,
  countryName,
  currencyCode,
  fmtAmount,
  fmtDateTime,
  fmtHours,
} from '@/lib/format'

interface Props {
  findingId: number | null
}

export function FindingDetailPane({ findingId }: Props) {
  const [detail, setDetail] = useState<FindingDetail | null>(null)
  const [graph, setGraph] = useState<FindingGraph | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (findingId == null) return
    let alive = true
    setDetail(null)
    setGraph(null)
    setError(null)
    Promise.all([api.getFinding(findingId), api.getGraph(findingId)])
      .then(([d, g]) => {
        if (!alive) return
        setDetail(d)
        setGraph(g)
      })
      .catch((e) => alive && setError(String(e)))
    return () => {
      alive = false
    }
  }, [findingId])

  if (findingId == null) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--color-fg-muted)]">
        Select a finding to inspect its graph.
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="glass max-w-md rounded-xl border-[var(--color-sev-critical)]/40 p-6 text-sm text-[var(--color-sev-critical)]">
          {error}
        </div>
      </div>
    )
  }

  if (!detail || !graph) {
    return (
      <div className="grid h-full grid-cols-1 gap-4 p-6 lg:grid-cols-[minmax(340px,400px)_1fr]">
        <div className="glass animate-pulse rounded-2xl bg-white/[0.02]" />
        <div className="glass animate-pulse rounded-2xl bg-white/[0.02]" />
      </div>
    )
  }

  const ccy = currencyCode(detail.currency)
  const parties = graph.entities.filter((e) => e.entity_type === 'Party')

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* hero header */}
      <div className="border-b border-[var(--color-border)] px-8 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <SeverityPill severity={detail.severity} />
              <span className="text-[10px] font-medium uppercase tracking-widest text-[var(--color-fg-muted)]">
                {detail.finding_type.replace(/_/g, ' ')} · {detail.assessment_id}
              </span>
              <span className="mono text-[10px] text-[var(--color-fg-dim)]">
                #{detail.finding_id}
              </span>
            </div>
            <h1 className="mt-2 text-[22px] font-semibold leading-tight text-[var(--color-fg)]">
              {circularTitle(detail.title)}
            </h1>
            {detail.description && (
              <p className="mt-1.5 max-w-[68ch] text-[13px] leading-relaxed text-[var(--color-fg-muted)]">
                {detail.description}
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1 text-right">
            <span className="text-[10px] uppercase tracking-widest text-[var(--color-fg-dim)]">
              First hop
            </span>
            <span className="mono text-[12px] text-[var(--color-fg)]">
              {fmtDateTime(detail.sla_trigger_date)}
            </span>
            <span className="text-[10px] text-[var(--color-fg-muted)]">
              SLA due {fmtDateTime(detail.sla_due_date)}
            </span>
          </div>
        </div>

        {/* stat strip */}
        <div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-6">
          <Stat
            label="Hops"
            value={detail.hop_count != null ? String(detail.hop_count) : '—'}
          />
          <Stat
            label="Time span"
            value={fmtHours(detail.time_span_hours)}
            sub="across ring"
          />
          <Stat label="Currency" value={ccy || '—'} />
          <Stat
            label="Min / max"
            value={`${fmtAmount(detail.amount_min)} · ${fmtAmount(detail.amount_max)}`}
            sub={`ratio ${detail.amount_ratio ?? '—'}`}
            compact
          />
          <Stat
            label="Banks"
            value={String(detail.bank_count ?? 0)}
            sub={detail.banks?.join(' · ') ?? ''}
            compact
          />
          <Stat
            label="Countries"
            value={String(detail.country_count ?? 0)}
            sub={(detail.countries ?? []).map((c) => `${countryFlag(c)} ${c}`).join(' · ')}
            compact
          />
        </div>
      </div>

      {/* body */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-5 p-5 lg:grid-cols-[minmax(320px,380px)_1fr]">
        {/* left: metadata cards */}
        <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1">
          <Card title="Parties in the ring">
            <ul className="space-y-2.5">
              {parties.map((p) => (
                <li
                  key={p.entity_id}
                  className="glass flex items-center gap-3 rounded-lg px-3 py-2"
                >
                  <span className="text-xl leading-none">{countryFlag(p.country)}</span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-semibold text-[var(--color-fg)]">
                      {p.display_name}
                    </div>
                    <div className="mono truncate text-[10px] text-[var(--color-fg-muted)]">
                      {p.entity_id} · {countryName(p.country)}
                    </div>
                  </div>
                  <RiskBadge tier={p.risk_tier} />
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Regulatory controls mapped">
            <div className="grid grid-cols-1 gap-2">
              <ControlRow label="BSA" value={detail.control_bsa} />
              <ControlRow label="FATF" value={detail.control_fatf} />
              <ControlRow label="EU AMLD" value={detail.control_eu_amld} />
            </div>
            <p className="mt-3 text-[10px] leading-relaxed text-[var(--color-fg-dim)]">
              Shape parity with <span className="mono">sds-product-em</span>'s NIST / PCI /
              SCF control mapping — swapped for AML regimes.
            </p>
          </Card>

          <Card title="Graph traversal" compact>
            <p className="text-[11px] leading-relaxed text-[var(--color-fg-muted)]">
              Surfaced by a recursive 3-way join over{' '}
              <span className="mono text-[var(--color-fg)]">silver.transfers_to</span>{' '}
              — chronological hops, same currency, min amount {'>'} 1,000, max/min amount
              ratio ≤ 1.5, time span ≤ 14 days. The detector never reads{' '}
              <span className="mono">bronze.is_laundering</span> — the label is reserved
              for post-hoc validation.
            </p>
          </Card>
        </div>

        {/* right: graph */}
        <section className="glass relative flex min-h-0 flex-col overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2.5">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-widest text-[var(--color-fg-muted)]">
                Ring graph
              </div>
              <div className="text-[10px] text-[var(--color-fg-dim)]">
                3 accounts · {detail.party_count} parties · {detail.bank_count} banks ·{' '}
                {graph.edges.length} transfers
              </div>
            </div>
            <div className="mono text-[10px] text-[var(--color-fg-dim)]">
              gold.finding_entity · gold.finding_edge
            </div>
          </div>
          <div className="min-h-0 flex-1">
            <RingGraph graph={graph} />
          </div>
        </section>
      </div>
    </div>
  )
}

// trim the "3-hop circular fund flow: " prefix and show just the cycle notation
function circularTitle(title: string): string {
  const idx = title.indexOf(': ')
  return idx >= 0 ? title.slice(idx + 2) : title
}

function Stat({
  label,
  value,
  sub,
  compact,
}: {
  label: string
  value: string
  sub?: string
  compact?: boolean
}) {
  return (
    <div className="glass rounded-lg px-3 py-2">
      <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-[var(--color-fg-dim)]">
        {label}
      </div>
      <div
        className={`mt-0.5 ${compact ? 'text-[13px]' : 'text-[18px]'} font-semibold tabular-nums text-[var(--color-fg)]`}
      >
        {value}
      </div>
      {sub && (
        <div className="mt-0.5 truncate text-[10px] text-[var(--color-fg-muted)]">{sub}</div>
      )}
    </div>
  )
}

function Card({
  title,
  compact,
  children,
}: {
  title: string
  compact?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="glass rounded-2xl">
      <div
        className={`border-b border-[var(--color-border)] ${
          compact ? 'px-4 py-2' : 'px-4 py-3'
        }`}
      >
        <div className="text-[11px] font-semibold uppercase tracking-widest text-[var(--color-fg-muted)]">
          {title}
        </div>
      </div>
      <div className={compact ? 'p-3' : 'p-3.5'}>{children}</div>
    </div>
  )
}

function RiskBadge({ tier }: { tier: string | null }) {
  if (!tier) return null
  const tone: Record<string, string> = {
    LOW: 'bg-[rgba(109,211,206,0.12)] text-[var(--color-sev-low)] ring-[rgba(109,211,206,0.35)]',
    MEDIUM:
      'bg-[rgba(255,200,87,0.12)] text-[var(--color-sev-medium)] ring-[rgba(255,200,87,0.35)]',
    HIGH: 'bg-[rgba(255,138,76,0.12)] text-[var(--color-sev-high)] ring-[rgba(255,138,76,0.35)]',
  }
  return (
    <span
      className={`mono inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider ring-1 ${
        tone[tier] ?? 'text-[var(--color-fg-muted)] ring-[var(--color-border)]'
      }`}
    >
      {tier}
    </span>
  )
}

function ControlRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mono shrink-0 rounded bg-white/[0.04] px-1.5 py-0.5 text-[9px] font-semibold tracking-wider text-[var(--color-accent-bright)] ring-1 ring-inset ring-[rgba(192,132,252,0.25)]">
        {label}
      </span>
      <span className="text-[11px] leading-snug text-[var(--color-fg)]">{value ?? '—'}</span>
    </div>
  )
}
