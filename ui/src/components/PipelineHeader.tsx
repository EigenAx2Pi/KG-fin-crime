const STAGES = [
  { label: 'CSV', sub: 'AMLSim HI-Small', color: 'text-[var(--color-fg-dim)]' },
  { label: 'Bronze', sub: 'raw mirror', color: 'text-[var(--color-bronze)]' },
  { label: 'Silver', sub: 'KG + assessment', color: 'text-[var(--color-silver)]' },
  { label: 'Gold', sub: 'published findings', color: 'text-[var(--color-gold)]' },
  { label: 'UI', sub: 'this view', color: 'text-[var(--color-accent-bright)]' },
]

export function PipelineHeader() {
  return (
    <header className="glass relative z-10 flex items-center gap-6 border-b border-[var(--color-border)] px-6 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-purple-500/30 to-cyan-400/20 text-lg font-bold text-[var(--color-accent-bright)] ring-1 ring-[var(--color-border-strong)]">
          KG
        </div>
        <div className="min-w-0 leading-tight">
          <div className="truncate text-sm font-semibold text-[var(--color-fg)]">
            KG-fin-crime
          </div>
          <div className="truncate text-[11px] text-[var(--color-fg-muted)]">
            Knowledge graph for financial crime · Prevalent SDS pattern
          </div>
        </div>
      </div>

      <div className="hidden items-center gap-2 md:flex">
        {STAGES.map((s, i) => (
          <div key={s.label} className="flex items-center gap-2">
            <div className="flex flex-col items-start">
              <span
                className={`text-[11px] font-semibold uppercase tracking-[0.1em] ${s.color}`}
              >
                {s.label}
              </span>
              <span className="text-[10px] text-[var(--color-fg-dim)]">{s.sub}</span>
            </div>
            {i < STAGES.length - 1 && (
              <svg
                className="text-[var(--color-fg-dim)]"
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M5 12h14M13 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <div className="hidden text-right text-[10px] text-[var(--color-fg-muted)] lg:block">
          Same pipeline pattern as
          <br />
          <span className="text-[var(--color-fg)]">sds-solution-ei · sds-product-em</span>
        </div>
      </div>
    </header>
  )
}
