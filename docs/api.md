# KG-fin-crime API — UI integration guide

Spec for the partner building the UI. Everything needed to wire a frontend to the existing FastAPI service over `gold.*`.

---

## 1. Run the backend

```bash
# from repo/ (Postgres must be up via `docker compose up -d`, data loaded)
source .venv/bin/activate
uvicorn api.main:app --reload
# API at http://127.0.0.1:8000
# OpenAPI / Swagger UI at http://127.0.0.1:8000/docs
```

CORS is wide open (`allow_origins=["*"]`) so any local dev server can hit it.

---

## 2. Data model at a glance

**Three finding typologies** — they all flow through the *same* endpoints with the same response shape. Some fields are typology-specific (null for others):

| `finding_type` | Meaning | Fields populated | Key summary stats |
|---|---|---|---|
| `CIRCULAR_FLOW` | 3-hop laundering ring (graph-native, unsupervised) | `hop_count=3`, `amount_ratio`, cycle-shaped | `hops`, `amount_ratio`, `payment_formats[]` |
| `MULE_HUB` | Fan-in / fan-out account (graph-native, unsupervised) | `hop_count=null`, `amount_ratio=null` | `in_degree`, `out_degree`, `balance_ratio` |
| `LAUNDERING_EXPOSURE` | Account flagged `IsLaundering=1` in ground truth (supervised) | `hop_count=null`, `amount_ratio=null` | `labeled_edges`, `labeled_amount_total` |

**Severity** (sort priority, highest first): `CRITICAL` → `HIGH` → `MEDIUM` → `LOW` → `INFORMATIONAL`

**Entity types** inside `/graph`: `Account`, `Party`, `FinancialInstitution`

**Roles** (entity's role in the finding):
- Circular flow: `ring_member`, `account_owner`, `custodian_bank`
- Mule hub: `mule_hub`, `account_owner`, `custodian_bank`, `inbound_counterparty`, `outbound_counterparty`
- Laundering exposure: `exposed_account`, `account_owner`, `custodian_bank`, `inbound_counterparty`, `outbound_counterparty`

**Edge types** inside `/graph`: `transfers_to` (account → account). Each edge carries its `fin_txn_id` back to `silver.financial_transaction`.

---

## 3. Endpoints

### `GET /healthz`

Liveness probe. Returns `{"ok": true}`.

### `GET /findings?severity=<S>&limit=<N>`

List findings, already sorted by severity (CRITICAL first) then `detected_at DESC`.

- `severity` — optional. One of `INFORMATIONAL | LOW | MEDIUM | HIGH | CRITICAL`.
- `limit` — optional int, default 50, max 500.

```ts
type Severity = 'INFORMATIONAL' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

interface FindingSummary {
  finding_id: number
  severity: Severity
  finding_type: string              // 'CIRCULAR_FLOW' | 'MULE_HUB' | 'LAUNDERING_EXPOSURE'
  title: string
  detected_at: string               // ISO timestamp
  currency: string | null           // e.g. 'Saudi Riyal', 'US Dollar'
  amount_min: string | null         // NUMERIC serialized as string — parse with Number()
  amount_max: string | null
  time_span_hours: number | null
  party_count: number | null        // distinct parties involved
  bank_count: number | null         // distinct banks involved
  country_count: number | null      // distinct countries of party residence
  countries: string[] | null        // ISO-2 codes, e.g. ['AE','GB','NL']
  banks: string[] | null            // human bank names, e.g. ['Bank 0121','Bank 0222']
}
```

**Sample:**

```bash
curl 'http://127.0.0.1:8000/findings?severity=HIGH&limit=3'
```

```json
[
  {
    "finding_id": 81,
    "severity": "HIGH",
    "finding_type": "CIRCULAR_FLOW",
    "title": "3-hop circular fund flow: 0223:8119F8CC0 -> 0222:811D80C30 -> 0121:8000E1590 -> 0223:8119F8CC0",
    "detected_at": "2026-04-24T04:00:12.123456",
    "currency": "Saudi Riyal",
    "amount_min": "51178.8000",
    "amount_max": "56544.7400",
    "time_span_hours": 77,
    "party_count": 3, "bank_count": 3, "country_count": 3,
    "countries": ["AE","GB","NL"],
    "banks": ["Bank 0121","Bank 0222","Bank 0223"]
  }
]
```

### `GET /findings/{finding_id}`

Full detail for one finding. Superset of the list shape.

```ts
interface FindingDetail extends FindingSummary {
  assessment_id: string             // 'circular_flow_v1' | 'mule_hub_v1' | 'laundering_exposure_v1'
  description: string | null
  hop_count: number | null          // circular-flow only (always 3); null for other typologies
  amount_ratio: string | null       // max/min, circular-flow only
  control_bsa: string | null        // 'BSA 31 CFR 1020.320 (Suspicious Activity Reports)'
  control_fatf: string | null       // 'FATF R.20 (Reporting of suspicious transactions)'
  control_eu_amld: string | null    // 'EU AMLD — Directive 2015/849 Art. 33'
  sla_trigger_date: string | null   // ISO timestamp (first hop)
  sla_due_date: string | null       // trigger + sla_duration
  sla_duration: string | null       // ISO 8601 duration, e.g. 'P3D' (3 days)
}
```

**Sample:**

```bash
curl http://127.0.0.1:8000/findings/81
```

```json
{
  "finding_id": 81,
  "assessment_id": "circular_flow_v1",
  "finding_type": "CIRCULAR_FLOW",
  "severity": "HIGH",
  "title": "3-hop circular fund flow: 0223:8119F8CC0 -> 0222:811D80C30 -> 0121:8000E1590 -> 0223:8119F8CC0",
  "description": "Ring of 3 distinct accounts returning funds to origin over 77 hours. Amount range 51178.8000-56544.7400 Saudi Riyal.",
  "detected_at": "2026-04-24T04:00:12",
  "hop_count": 3,
  "currency": "Saudi Riyal",
  "amount_min": "51178.8000", "amount_max": "56544.7400", "amount_ratio": "1.1048",
  "time_span_hours": 77,
  "control_bsa": "31 CFR 1020.320 (Suspicious Activity Reports)",
  "control_fatf": "R.20 (Reporting of suspicious transactions)",
  "control_eu_amld": "Directive 2015/849 Art. 33",
  "sla_trigger_date": "2022-09-05T11:21:00",
  "sla_due_date":    "2022-09-08T11:21:00",
  "sla_duration":    "P3D",
  "party_count": 3, "bank_count": 3, "country_count": 3,
  "countries": ["AE","GB","NL"],
  "banks": ["Bank 0121","Bank 0222","Bank 0223"]
}
```

Returns **404** if `finding_id` doesn't exist.

### `GET /findings/{finding_id}/graph`

The drill-down payload for a graph view. Entities + directed edges for the finding.

```ts
interface GraphEntity {
  entity_type: 'Account' | 'Party' | 'FinancialInstitution'
  entity_id: string                 // account_key / party_id / fse_id
  role: string | null               // see Roles table above
  display_name: string | null       // party name, bank name, or the account key
  country: string | null            // Party only — ISO-2 code
  risk_tier: string | null          // Party only — 'LOW' | 'MEDIUM' | 'HIGH'
  bank_id: string | null            // Account only
  bank_name: string | null          // Account + FinancialInstitution
  // owner_party_id: string | null  ← exists on feat/ui branch only; null elsewhere
}

interface GraphEdge {
  hop_order: number                 // 1..N (cycle order for circular; top-N by amount for mule/exposure)
  edge_type: 'transfers_to'
  from_account_key: string
  to_account_key: string
  from_bank_id: string | null
  to_bank_id: string | null
  fin_txn_id: number | null
  amount: string | null             // NUMERIC as string
  currency: string | null
  event_timestamp: string | null    // ISO
  payment_format: string | null     // 'ACH' | 'Wire' | 'Cheque' | 'Cash' | 'Reinvestment' | ...
}

interface FindingGraph {
  finding_id: number
  entities: GraphEntity[]
  edges: GraphEdge[]
}
```

**Sample (hero ring):**

```bash
curl http://127.0.0.1:8000/findings/81/graph
```

Returns 9 entities (3 Accounts + 3 Parties + 3 FinancialInstitutions) and 3 edges (the ring hops).

**Sample (mule hub):**

```bash
curl http://127.0.0.1:8000/findings/117/graph
```

Returns ~11 entities (1 hub Account + 1 owner Party + 1 custodian FI + up to 5 inbound + up to 5 outbound counterparty Accounts) and 10 edges (top-5 inbound + top-5 outbound transfers by amount).

---

## 4. Three sample finding IDs to test against

| ID | Typology | Severity | What it looks like |
|---|---|---|---|
| **81** | `CIRCULAR_FLOW` | HIGH | The hero ring — 3 accounts × 3 banks × 3 countries (AE/GB/NL), Ava Miller + Mia Patel + Lucas de Vries, 77h span, 51k–56k SAR. Ideal demo finding. |
| **110** (may shift) | `MULE_HUB` | CRITICAL | Fan-in/fan-out — account `070:100428660`, 545 in / 14,230 out counterparties. |
| **150** (may shift) | `LAUNDERING_EXPOSURE` | CRITICAL | Same account `070:100428660`, 243 labeled transfers. |

IDs can shift if detectors are re-run. Look them up via:

```bash
curl 'http://127.0.0.1:8000/findings?limit=500' \
  | jq 'group_by(.finding_type)[] | {type: .[0].finding_type, ids: map(.finding_id)[:3]}'
```

---

## 5. Field-level UI guidance

- **Always-safe fields** (populated for every typology): `finding_id`, `severity`, `finding_type`, `title`, `detected_at`, `currency`, `amount_min`, `amount_max`, `time_span_hours`, `party_count`, `bank_count`, `country_count`, `countries`, `banks`, `sla_*`, `control_*`.
- **Circular-flow only** (render conditionally): `hop_count`, `amount_ratio`.
- **Amounts are strings** (Postgres NUMERIC serializes as string). Parse with `Number()` or `Intl.NumberFormat` for display.
- **Timestamps are ISO strings without timezone** (treat as UTC).
- **`finding_type`** is screaming-snake — use `.replace(/_/g, ' ')` + title-case for display.

---

## 6. Suggested UI scope

Two views carry everything:

- **List view**: `/findings?severity=...&limit=...` → cards/rows. Show severity pill, title, `amount_max + currency`, countries (flags + codes), `bank_count` / `party_count`.
- **Detail view**: split pane.
  - **Left**: fields from `/findings/{id}` (control mapping + SLA as pills, parties as a list with flag/country/risk).
  - **Right**: `/findings/{id}/graph` rendered with a graph lib. Cytoscape.js with the `cose-bilkent` layout works well; nodes styled by `entity_type`, edges colored by `edge_type`.

There's a working reference implementation on the `feat/ui` branch of https://github.com/NIKHIL-523/KG-fin-crime — crib styles, component shapes, and the Cytoscape config from `ui/src/components/RingGraph.tsx` if useful.

---

## 7. Branches

| Branch | State |
|---|---|
| `main` | Baseline — full pipeline + API + all three assessments (188 findings). **This is what you build the UI on top of.** |
| `feat/ui` | Reference UI implementation — Vite + React + TS + Tailwind + Cytoscape.js. Ships `owner_party_id` on `GraphEntity` (used to draw party→account edges). Crib styles, component shapes, and the Cytoscape config from `ui/src/components/RingGraph.tsx` if useful. |

If your UI wants the `owner_party_id` field on Account entities (to wire party→account edges), cherry-pick the two-line column addition from `feat/ui`'s `schema/004_gold.sql` + `src/gold/publish.py` + `src/api/models.py` + `src/api/routes/findings.py` and re-run `python -m gold.publish`.
