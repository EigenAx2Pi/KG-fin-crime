import { useEffect, useMemo, useRef } from 'react'
import cytoscape from 'cytoscape'
import type { Core, ElementDefinition, StylesheetJson } from 'cytoscape'
// @ts-expect-error — no types shipped
import coseBilkent from 'cytoscape-cose-bilkent'
import type { FindingGraph } from '@/lib/types'
import { countryFlag } from '@/lib/format'

let registered = false
function ensureRegistered() {
  if (!registered) {
    cytoscape.use(coseBilkent)
    registered = true
  }
}

const STYLE: StylesheetJson = [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      color: '#e5e7ff',
      'text-valign': 'center',
      'text-halign': 'center',
      'font-family': 'Inter, system-ui, sans-serif',
      'font-size': 11,
      'font-weight': 600,
      'text-wrap': 'wrap',
      'text-max-width': '130px',
    },
  },
  {
    selector: 'node[type="account"]',
    style: {
      shape: 'ellipse',
      width: 72,
      height: 72,
      'background-color': '#1a1c2a',
      'background-opacity': 1,
      'border-width': 2.5,
      'border-color': '#c084fc',
      'border-opacity': 0.85,
      'font-family': 'JetBrains Mono, ui-monospace, monospace',
      'font-size': 9,
      'text-outline-color': '#0a0b14',
      'text-outline-width': 3,
    },
  },
  {
    selector: 'node[type="party"]',
    style: {
      shape: 'round-rectangle',
      width: 150,
      height: 46,
      'background-color': '#12131e',
      'border-width': 1.5,
      'border-color': '#6dd3ce',
      'border-opacity': 0.6,
    },
  },
  { selector: 'node[type="party"][riskTier="MEDIUM"]', style: { 'border-color': '#ffc857' } },
  { selector: 'node[type="party"][riskTier="HIGH"]', style: { 'border-color': '#ff8a4c' } },
  { selector: 'node[type="party"][riskTier="CRITICAL"]', style: { 'border-color': '#ff4d6d' } },
  {
    selector: 'node[type="bank"]',
    style: {
      shape: 'round-diamond',
      width: 92,
      height: 46,
      'background-color': '#0f1019',
      'border-width': 1,
      'border-color': 'rgba(255,255,255,0.18)',
      color: '#8b8fa8',
      'font-size': 10,
      'font-weight': 500,
    },
  },
  {
    selector: 'edge',
    style: {
      'curve-style': 'bezier',
      width: 1.2,
      'line-color': 'rgba(255,255,255,0.12)',
      'target-arrow-color': 'rgba(255,255,255,0.12)',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.9,
    },
  },
  {
    selector: 'edge[type="cycle"]',
    style: {
      width: 2.6,
      'line-color': '#c084fc',
      'target-arrow-color': '#c084fc',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 1.2,
      label: 'data(label)',
      color: '#e5e7ff',
      'font-size': 10,
      'font-weight': 600,
      'font-family': 'JetBrains Mono, ui-monospace, monospace',
      'text-background-color': '#12131e',
      'text-background-opacity': 0.92,
      'text-background-padding': '4px',
      'text-background-shape': 'roundrectangle',
      'text-border-color': 'rgba(192,132,252,0.4)',
      'text-border-opacity': 1,
      'text-border-width': 1,
      'text-rotation': 'autorotate',
      'text-margin-y': -2,
    },
  },
  {
    selector: 'edge[type="hasAccount"]',
    style: {
      'line-style': 'dashed',
      'line-dash-pattern': [6, 4],
      'target-arrow-shape': 'none',
      'line-color': 'rgba(109,211,206,0.35)',
      width: 1.2,
    },
  },
  {
    selector: 'edge[type="heldAt"]',
    style: {
      'line-style': 'dashed',
      'line-dash-pattern': [4, 4],
      'target-arrow-shape': 'none',
      'line-color': 'rgba(255,255,255,0.08)',
      width: 1,
    },
  },
]

export function RingGraph({ graph }: { graph: FindingGraph }) {
  ensureRegistered()
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)

  const elements = useMemo<ElementDefinition[]>(() => {
    const accounts = graph.entities.filter((e) => e.entity_type === 'Account')
    const parties = graph.entities.filter((e) => e.entity_type === 'Party')
    const banks = graph.entities.filter((e) => e.entity_type === 'FinancialInstitution')

    const accId = (k: string) => `acc:${k}`
    const partyId = (k: string) => `party:${k}`
    const bankId = (k: string) => `bank:${k}`

    const nodes: ElementDefinition[] = [
      ...accounts.map((a) => ({
        data: {
          id: accId(a.entity_id),
          type: 'account',
          label: a.entity_id.split(':')[1] ?? a.entity_id,
          fullKey: a.entity_id,
          bankId: a.bank_id,
          ownerPartyId: a.owner_party_id,
        },
      })),
      ...parties.map((p) => ({
        data: {
          id: partyId(p.entity_id),
          type: 'party',
          label: `${countryFlag(p.country)}  ${p.display_name ?? p.entity_id}\n${p.country ?? ''} · ${p.risk_tier ?? ''}`,
          country: p.country,
          riskTier: p.risk_tier,
        },
      })),
      ...banks.map((b) => ({
        data: {
          id: bankId(b.entity_id),
          type: 'bank',
          label: b.display_name ?? b.entity_id,
        },
      })),
    ]

    const cycleEdges: ElementDefinition[] = graph.edges.map((e) => {
      const amt = e.amount ? Number(e.amount) : 0
      const label = amt
        ? `${amt.toLocaleString('en-US', { maximumFractionDigits: 0 })} ${e.currency ?? ''}`
        : ''
      return {
        data: {
          id: `cycle:${e.hop_order}`,
          source: accId(e.from_account_key),
          target: accId(e.to_account_key),
          label,
          type: 'cycle',
          hop: e.hop_order,
        },
      }
    })

    const heldAtEdges: ElementDefinition[] = accounts
      .filter((a) => a.bank_id)
      .map((a) => ({
        data: {
          id: `held:${a.entity_id}`,
          source: accId(a.entity_id),
          target: bankId(a.bank_id!),
          type: 'heldAt',
        },
      }))

    const ownershipEdges: ElementDefinition[] = accounts
      .filter((a) => a.owner_party_id)
      .map((a) => ({
        data: {
          id: `owns:${a.owner_party_id}-${a.entity_id}`,
          source: partyId(a.owner_party_id!),
          target: accId(a.entity_id),
          type: 'hasAccount',
        },
      }))

    return [...nodes, ...cycleEdges, ...heldAtEdges, ...ownershipEdges]
  }, [graph])

  useEffect(() => {
    if (!containerRef.current) return
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: STYLE,
      layout: {
        name: 'cose-bilkent',
        animate: 'end',
        animationDuration: 600,
        idealEdgeLength: 140,
        nodeRepulsion: 9000,
        edgeElasticity: 0.2,
        gravity: 0.3,
        numIter: 2500,
        randomize: true,
      } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.2,
      minZoom: 0.3,
      maxZoom: 2.5,
    })
    cyRef.current = cy

    cy.ready(() => {
      cy.fit(undefined, 60)
    })

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [elements])

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      <div className="pointer-events-none absolute left-4 top-4 flex flex-wrap gap-3 text-[10px] text-[var(--color-fg-muted)]">
        <LegendChip color="#c084fc" label="transfers_to (cycle)" />
        <LegendChip color="#6dd3ce" label="hasAccount" dashed />
        <LegendChip color="rgba(255,255,255,0.28)" label="isHeldAt" dashed />
      </div>
    </div>
  )
}

function LegendChip({
  color,
  label,
  dashed,
}: {
  color: string
  label: string
  dashed?: boolean
}) {
  return (
    <span className="glass inline-flex items-center gap-2 rounded-full px-2.5 py-1">
      <svg width="20" height="6">
        <line
          x1="0"
          y1="3"
          x2="20"
          y2="3"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={dashed ? '4 3' : undefined}
        />
      </svg>
      <span className="mono">{label}</span>
    </span>
  )
}
