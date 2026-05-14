import type { FindingDetail, FindingGraph, FindingSummary, Severity } from '@/lib/types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  listFindings: (severity?: Severity, limit = 200) => {
    const q = new URLSearchParams()
    if (severity) q.set('severity', severity)
    q.set('limit', String(limit))
    return get<FindingSummary[]>(`/findings?${q}`)
  },
  getFinding: (id: number) => get<FindingDetail>(`/findings/${id}`),
  getGraph: (id: number) => get<FindingGraph>(`/findings/${id}/graph`),
}
