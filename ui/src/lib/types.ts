export type Severity = 'INFORMATIONAL' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface FindingSummary {
  finding_id: number
  severity: Severity
  finding_type: string
  title: string
  detected_at: string
  currency: string | null
  amount_min: string | null
  amount_max: string | null
  time_span_hours: number | null
  party_count: number | null
  bank_count: number | null
  country_count: number | null
  countries: string[] | null
  banks: string[] | null
}

export interface FindingDetail extends FindingSummary {
  assessment_id: string
  description: string | null
  hop_count: number | null
  amount_ratio: string | null
  control_bsa: string | null
  control_fatf: string | null
  control_eu_amld: string | null
  sla_trigger_date: string | null
  sla_due_date: string | null
  sla_duration: string | null
}

export interface GraphEntity {
  entity_type: 'Account' | 'Party' | 'FinancialInstitution'
  entity_id: string
  role: string | null
  display_name: string | null
  country: string | null
  risk_tier: string | null
  bank_id: string | null
  bank_name: string | null
  owner_party_id: string | null
}

export interface GraphEdge {
  hop_order: number
  edge_type: string
  from_account_key: string
  to_account_key: string
  from_bank_id: string | null
  to_bank_id: string | null
  fin_txn_id: number | null
  amount: string | null
  currency: string | null
  event_timestamp: string | null
  payment_format: string | null
}

export interface FindingGraph {
  finding_id: number
  entities: GraphEntity[]
  edges: GraphEdge[]
}
