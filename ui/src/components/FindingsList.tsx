import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { FindingSummary, Severity } from '@/lib/types'
import { FindingCard } from '@/components/FindingCard'

const FILTERS: Array<{ label: string; value: Severity | 'ALL' }> = [
  { label: 'All', value: 'ALL' },
  { label: 'High', value: 'HIGH' },
  { label: 'Medium', value: 'MEDIUM' },
]

interface Props {
  selectedId: number | null
  onSelect: (id: number) => void
}

export function FindingsList({ selectedId, onSelect }: Props) {
  const [filter, setFilter] = useState<Severity | 'ALL'>('ALL')
  const [findings, setFindings] = useState<FindingSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setFindings(null)
    setError(null)
    api
      .listFindings(filter === 'ALL' ? undefined : filter, 300)
      .then((d) => {
        if (!alive) return
        setFindings(d)
        if (d.length && (selectedId == null || !d.find((f) => f.finding_id === selectedId))) {
          const hero = d.find((f) => f.finding_id === 81)
          onSelect(hero?.finding_id ?? d[0].finding_id)
        }
      })
      .catch((e) => alive && setError(String(e)))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter])

  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-elev)]/40">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-5 py-4">
        <div>
          <h2 className="text-[15px] font-semibold text-[var(--color-fg)]">Findings</h2>
          <p className="text-[11px] text-[var(--color-fg-muted)]">
            {findings
              ? `${findings.length} published to gold.finding`
              : 'Loading gold.finding …'}
          </p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-[var(--color-border)] px-4 py-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider transition ${
              filter === f.value
                ? 'bg-white/[0.08] text-[var(--color-fg)]'
                : 'text-[var(--color-fg-muted)] hover:text-[var(--color-fg)]'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {error && (
          <div className="rounded-lg border border-[var(--color-sev-critical)]/40 bg-[rgba(255,77,109,0.08)] p-3 text-sm text-[var(--color-sev-critical)]">
            {error}
          </div>
        )}
        {!findings && !error && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="glass h-[120px] animate-pulse rounded-xl bg-white/[0.02]"
              />
            ))}
          </div>
        )}
        {findings && findings.length === 0 && (
          <div className="py-10 text-center text-sm text-[var(--color-fg-muted)]">
            No findings match this filter.
          </div>
        )}
        {findings && findings.length > 0 && (
          <div className="space-y-2">
            {findings.map((f) => (
              <FindingCard
                key={f.finding_id}
                finding={f}
                selected={f.finding_id === selectedId}
                onClick={() => onSelect(f.finding_id)}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
