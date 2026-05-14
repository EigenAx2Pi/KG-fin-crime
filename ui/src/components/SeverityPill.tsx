import type { Severity } from '@/lib/types'

const TONE: Record<Severity, { bg: string; fg: string; dot: string; ring: string }> = {
  CRITICAL: {
    bg: 'bg-[rgba(255,77,109,0.12)]',
    fg: 'text-[var(--color-sev-critical)]',
    dot: 'bg-[var(--color-sev-critical)]',
    ring: 'ring-[rgba(255,77,109,0.35)]',
  },
  HIGH: {
    bg: 'bg-[rgba(255,138,76,0.12)]',
    fg: 'text-[var(--color-sev-high)]',
    dot: 'bg-[var(--color-sev-high)]',
    ring: 'ring-[rgba(255,138,76,0.35)]',
  },
  MEDIUM: {
    bg: 'bg-[rgba(255,200,87,0.12)]',
    fg: 'text-[var(--color-sev-medium)]',
    dot: 'bg-[var(--color-sev-medium)]',
    ring: 'ring-[rgba(255,200,87,0.35)]',
  },
  LOW: {
    bg: 'bg-[rgba(109,211,206,0.12)]',
    fg: 'text-[var(--color-sev-low)]',
    dot: 'bg-[var(--color-sev-low)]',
    ring: 'ring-[rgba(109,211,206,0.35)]',
  },
  INFORMATIONAL: {
    bg: 'bg-[rgba(122,162,247,0.12)]',
    fg: 'text-[var(--color-sev-info)]',
    dot: 'bg-[var(--color-sev-info)]',
    ring: 'ring-[rgba(122,162,247,0.35)]',
  },
}

export function SeverityPill({ severity, size = 'md' }: { severity: Severity; size?: 'sm' | 'md' }) {
  const t = TONE[severity]
  const pad = size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-[11px]'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold uppercase tracking-[0.08em] ring-1 ${t.bg} ${t.fg} ${t.ring} ${pad}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${t.dot} ring-pulse`} />
      {severity}
    </span>
  )
}
