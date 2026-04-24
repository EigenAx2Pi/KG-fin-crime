# KG-fin-crime — Data Model

End-to-end schema reference for the bronze → silver → gold medallion pipeline. All three layers live in one PostgreSQL database (`kgfincrime`), separated by schema name.

---

## 1. Architecture at a glance

```
  CSVs                bronze.*              silver.*                      silver.finding*              gold.*                  FastAPI + UI
  (AMLSim)      raw-loaded mirror     FIBO-aligned KG                   assessments & findings      display-ready projection
                                      (4 node types, 5 edges)           (3 typologies today)

  HI-Small_Trans.csv           ──►   financial_institution
  HI-Small_KYC_Customers.csv   ──►   party                              assessment_config           finding  (flattened)
  HI-Small_Account_            ──►   account                            finding                     finding_entity (denormalized)
  Customer_Link.csv            ──►   financial_transaction              finding_entity              finding_edge   (typed attrs)
                                     + 5 typed edge tables              finding_edge
```

**Pipeline modules** (all under `repo/src/`): `bronze.load`, `silver.transform`, `assessments.circular_flow`, `assessments.mule_hub`, `assessments.laundering_exposure`, `gold.publish`.

**Reference pattern**: entity/relationship shapes follow `sds-solution-ei/configs/documents/`; assessment/finding shape follows `sds-product-em` (NIST → BSA/FATF mapping swap). See `docs/kg-model.md` and `notes/reference-alignment.md` for full rationale.

---

## 2. Bronze layer — raw CSV mirrors

**Principle**: lossless mirror of the source CSVs. Minimal typing (timestamp, numeric), no joins, no derived columns. `is_laundering` is retained as ground truth on bronze **but must not be read by graph-native detectors** (see §7).

### `bronze.transactions_raw`

One row per transfer in `HI-Small_Trans.csv` (5,078,345 rows).

| Column | Type | Notes |
|---|---|---|
| `event_timestamp` | `TIMESTAMP NOT NULL` | `YYYY/MM/DD HH:MM` from the CSV |
| `from_bank` | `TEXT NOT NULL` | source bank id |
| `from_account` | `TEXT NOT NULL` | source account id |
| `to_bank` | `TEXT NOT NULL` | destination bank id |
| `to_account` | `TEXT NOT NULL` | destination account id |
| `amount_received` | `NUMERIC(20,4) NOT NULL` | amount at the beneficiary |
| `receiving_currency` | `TEXT NOT NULL` | e.g. `Saudi Riyal` |
| `amount_paid` | `NUMERIC(20,4) NOT NULL` | amount debited from originator |
| `payment_currency` | `TEXT NOT NULL` | often equals `receiving_currency` |
| `payment_format` | `TEXT NOT NULL` | `ACH`, `Wire`, `Cheque`, `Cash`, `Reinvestment`, … |
| `is_laundering` | `SMALLINT NOT NULL` | 0/1 ground-truth label — **supervised-only usage** |

### `bronze.kyc_customers_raw`

One row per customer in `HI-Small_KYC_Customers.csv` (515,088 rows).

| Column | Type | Notes |
|---|---|---|
| `customer_id` | `TEXT NOT NULL` | source customer id |
| `golden_customer_id` | `TEXT NOT NULL` | resolved "true" entity id (equals `customer_id` in this feed) |
| `record_source` | `TEXT` | e.g. `KYC` |
| `full_name` | `TEXT` | |
| `dob` | `DATE` | |
| `country` | `TEXT` | ISO-2 code (`AE`, `GB`, `NL`, …) |
| `address` | `TEXT` | free-form |
| `phone` | `TEXT` | |
| `email` | `TEXT` | |
| `government_id` | `TEXT` | |
| `risk_tier` | `TEXT` | `LOW` \| `MEDIUM` \| `HIGH` |

### `bronze.account_customer_link_raw`

Account ↔ customer ownership (515,088 rows).

| Column | Type | Notes |
|---|---|---|
| `account_key` | `TEXT NOT NULL` | `{bank_id}:{account_id}` — matches silver join key |
| `bank_id` | `TEXT NOT NULL` | |
| `account_id` | `TEXT NOT NULL` | |
| `customer_id` | `TEXT NOT NULL` | |
| `golden_customer_id` | `TEXT NOT NULL` | |
| `relationship` | `TEXT` | e.g. `PRIMARY_OWNER` |

---

## 3. Silver layer — FIBO-aligned knowledge graph

**Principle**: normalize bronze rows into a node/edge graph whose shape mirrors `sds-solution-ei/configs/documents/` (typed entity documents + typed relationship edges). 4 node types, 5 edge types.

### 3.1 Nodes

Each is a typed entity in the KG, FIBO-aligned.

#### `silver.party` (customer — FIBO: *Party*)

PK `party_id` (= `golden_customer_id`). 515,088 rows.

| Column | Type | Notes |
|---|---|---|
| `party_id` | `TEXT PRIMARY KEY` | |
| `source_customer_id` | `TEXT NOT NULL` | |
| `record_source` | `TEXT` | |
| `name` | `TEXT` | |
| `date_of_birth` | `DATE` | |
| `country_of_residence` | `TEXT` | feeds `gold.finding.countries[]` |
| `address_text` | `TEXT` | |
| `phone` | `TEXT` | |
| `email` | `TEXT` | |
| `government_id` | `TEXT` | |
| `risk_tier` | `TEXT` | `LOW` / `MEDIUM` / `HIGH` |

#### `silver.financial_institution` (FIBO: *Depository Institution*)

PK `fse_id`. One row per distinct `bank_id` seen in the data.

| Column | Type | Notes |
|---|---|---|
| `fse_id` | `TEXT PRIMARY KEY` | the bank id |
| `name` | `TEXT NOT NULL` | derived: `'Bank ' || bank_id` |

#### `silver.account` (FIBO: *Deposit Account*)

PK `account_key`. 515,088 rows.

| Column | Type | Notes |
|---|---|---|
| `account_key` | `TEXT PRIMARY KEY` | `{bank_id}:{account_id}` |
| `bank_id` | `TEXT NOT NULL` | FK → `silver.financial_institution(fse_id)` |
| `account_id` | `TEXT NOT NULL` | |
| `currency` | `TEXT` | optional, reserved (not currently populated) |

#### `silver.financial_transaction` (FIBO: *Payment / Financial Transaction*)

PK `fin_txn_id` — a surrogate `BIGINT` assigned by `ROW_NUMBER()` over the bronze rows at transform time, deterministic under ordered inputs. 5,078,345 rows.

| Column | Type | Notes |
|---|---|---|
| `fin_txn_id` | `BIGINT PRIMARY KEY` | |
| `event_timestamp` | `TIMESTAMP NOT NULL` | |
| `amount_paid` | `NUMERIC(20,4) NOT NULL` | |
| `payment_currency` | `TEXT NOT NULL` | |
| `amount_received` | `NUMERIC(20,4) NOT NULL` | |
| `receiving_currency` | `TEXT NOT NULL` | |
| `payment_format` | `TEXT NOT NULL` | |
| `source` | `TEXT` | origin feed filename |

**Note**: `is_laundering` is **not** propagated here (graph-native detectors must not see it).

### 3.2 Edges (typed relationships)

All edges are materialized tables. FK constraints wire them to the node PKs.

| Edge table | Direction | Semantics (FIBO) | Row count |
|---|---|---|---|
| `silver.has_account` | Party → Account | party holds the account | 515,088 |
| `silver.is_held_at` | Account → FinancialInstitution | account maintained by this FI | 515,088 |
| `silver.has_originating_account` | FinancialTransaction → Account | transaction originates from this source account | 5,078,345 |
| `silver.has_beneficiary_account` | FinancialTransaction → Account | transaction paid to this destination account | 5,078,345 |
| `silver.transfers_to` | Account → Account (derived convenience edge) | collapses the FinTxn intermediary for graph traversal | 5,078,345 |

#### `silver.has_account`

| Column | Type | Notes |
|---|---|---|
| `party_id` | `TEXT NOT NULL` FK | |
| `account_key` | `TEXT NOT NULL` FK | |
| `relationship` | `TEXT` | e.g. `PRIMARY_OWNER` |
| `source` | `TEXT` | |
| PK | `(party_id, account_key)` | |

#### `silver.is_held_at`

| Column | Type | Notes |
|---|---|---|
| `account_key` | `TEXT NOT NULL` FK | |
| `fse_id` | `TEXT NOT NULL` FK | |
| PK | `(account_key, fse_id)` | |

#### `silver.has_originating_account` / `silver.has_beneficiary_account`

| Column | Type | Notes |
|---|---|---|
| `fin_txn_id` | `BIGINT NOT NULL` FK, PK | one source + one dest per txn |
| `account_key` | `TEXT NOT NULL` FK | |

#### `silver.transfers_to` (the graph-traversal workhorse)

| Column | Type | Notes |
|---|---|---|
| `fin_txn_id` | `BIGINT PRIMARY KEY` FK | |
| `from_account_key` | `TEXT NOT NULL` FK | |
| `to_account_key` | `TEXT NOT NULL` FK | |
| `event_timestamp` | `TIMESTAMP NOT NULL` | |
| `amount` | `NUMERIC(20,4) NOT NULL` | = `amount_paid` on the originating side |
| `currency` | `TEXT NOT NULL` | = `payment_currency` |
| `payment_format` | `TEXT NOT NULL` | |

Indexes: `from_account_key`, `to_account_key`, `event_timestamp` — these drive the 3-way self-join in the circular-flow detector and the `GROUP BY` in the mule-hub detector.

---

## 4. Silver findings — assessments, findings, and their related entities/edges

Mirrors `sds-product-em`'s finding shape: **persisted assessment config → findings that cite it → related entities and edges for drill-down**. Swapped regulatory frame (NIST/PCI/SCF → BSA/FATF/EU AMLD).

### 4.1 `silver.assessment_config` (config-as-data)

One row per assessment typology (three today, framework accepts more).

| Column | Type | Notes |
|---|---|---|
| `assessment_id` | `TEXT PRIMARY KEY` | e.g. `circular_flow_v1`, `mule_hub_v1`, `laundering_exposure_v1` |
| `title` | `TEXT NOT NULL` | |
| `description` | `TEXT` | |
| `severity_default` | `TEXT NOT NULL` | the max severity this assessment can emit |
| `scope_query` | `TEXT NOT NULL` | natural-language / SQL snippet describing candidate rows |
| `success_condition` | `TEXT NOT NULL` | when does this fire (natural language) |
| `finding_config` | `JSONB NOT NULL` | thresholds, filters (e.g. `{"hops": 3, "max_amount_ratio": 1.5}`) |
| `control_mapping` | `JSONB` | `{"BSA": "...", "FATF": "...", "EU_AMLD": "..."}` |
| `sla_duration` | `INTERVAL` | e.g. `INTERVAL '72 hours'` |
| `created_at` | `TIMESTAMP DEFAULT now()` | |

**Seeded configs**:

| `assessment_id` | Type | Regime | SLA |
|---|---|---|---|
| `circular_flow_v1` | Graph-native | Unsupervised | 72h |
| `mule_hub_v1` | Graph-native | Unsupervised | 72h |
| `laundering_exposure_v1` | Label-driven | Supervised | 48h |

### 4.2 `silver.finding`

One row per detected finding (188 rows today).

| Column | Type | Notes |
|---|---|---|
| `finding_id` | `BIGINT PRIMARY KEY` | assigned by detector |
| `assessment_id` | `TEXT NOT NULL` FK → `silver.assessment_config` | which assessment fired |
| `finding_type` | `TEXT NOT NULL` | `CIRCULAR_FLOW` \| `MULE_HUB` \| `LAUNDERING_EXPOSURE` |
| `severity` | `TEXT NOT NULL` | `INFORMATIONAL` \| `LOW` \| `MEDIUM` \| `HIGH` \| `CRITICAL` |
| `title` | `TEXT NOT NULL` | |
| `description` | `TEXT` | |
| `detected_at` | `TIMESTAMP DEFAULT now()` | |
| `summary_stats` | `JSONB NOT NULL` | typology-specific stats (see §4.5) |
| `control_mapping` | `JSONB` | copied from `assessment_config` at detection time |
| `sla_trigger_date` | `TIMESTAMP` | usually the first hop / earliest flagged event |
| `sla_action_date` | `TIMESTAMP` | NULL until remediated |
| `sla_duration` | `INTERVAL` | copied from config |

### 4.3 `silver.finding_entity`

Related entities per finding (Account / Party / FinancialInstitution).

| Column | Type | Notes |
|---|---|---|
| `finding_id` | `BIGINT NOT NULL` FK | `ON DELETE CASCADE` |
| `entity_type` | `TEXT NOT NULL` | `Account` / `Party` / `FinancialInstitution` |
| `entity_id` | `TEXT NOT NULL` | `account_key` / `party_id` / `fse_id` |
| `role` | `TEXT` | see Role taxonomy below |
| PK | `(finding_id, entity_type, entity_id)` | |

**Role taxonomy** (role is typology-dependent):

- **Circular flow**: `ring_member` (Account), `account_owner` (Party), `custodian_bank` (FI).
- **Mule hub**: `mule_hub` (hub Account), `account_owner` (Party), `custodian_bank` (FI), `inbound_counterparty` / `outbound_counterparty` (top-5 Accounts per side by amount).
- **Laundering exposure**: `exposed_account` (Account), `account_owner` (Party), `custodian_bank` (FI), `inbound_counterparty` / `outbound_counterparty` (top-3 Accounts per side by labeled amount).

### 4.4 `silver.finding_edge`

Edges per finding — references `silver.financial_transaction` by `fin_txn_id`.

| Column | Type | Notes |
|---|---|---|
| `finding_id` | `BIGINT NOT NULL` FK | |
| `hop_order` | `SMALLINT NOT NULL` | 1..N; cycle order for circular, top-N by amount for mule/exposure |
| `edge_type` | `TEXT NOT NULL` | `transfers_to` today |
| `from_entity` | `TEXT NOT NULL` | account_key |
| `to_entity` | `TEXT NOT NULL` | account_key |
| `fin_txn_id` | `BIGINT` FK → `silver.financial_transaction` | provenance |
| `attrs` | `JSONB` | amount / currency / ts / payment_format / direction / is_laundering |
| PK | `(finding_id, hop_order)` | |

### 4.5 `summary_stats` JSONB — per-typology shape

All three typologies write to the same `silver.finding.summary_stats` column with different keys. Gold flattens a common subset into typed columns; the rest stays available in silver for analytics.

| Key | Type | circular_flow | mule_hub | laundering_exposure |
|---|---|:---:|:---:|:---:|
| `currency` | string | ✓ | ✓ (dominant) | ✓ (dominant) |
| `amount_min` | numeric | ✓ | ✓ | ✓ |
| `amount_max` | numeric | ✓ | ✓ | ✓ |
| `time_span_hours` | int | ✓ | ✓ | ✓ |
| `hops` | int (=3) | ✓ | — | — |
| `amount_ratio` | numeric | ✓ (max/min) | — | — |
| `payment_formats` | array[string] | ✓ | — | — |
| `accounts` | array[string] | ✓ (ring members) | — | — |
| `in_degree` | int | — | ✓ | — |
| `out_degree` | int | — | ✓ | — |
| `in_txn_count` | int | — | ✓ | — |
| `out_txn_count` | int | — | ✓ | — |
| `in_amount_total` | numeric | — | ✓ | — |
| `out_amount_total` | numeric | — | ✓ | — |
| `balance_ratio` | numeric | — | ✓ (out/in) | — |
| `labeled_edges` | int | — | — | ✓ |
| `distinct_labeled_txns` | int | — | — | ✓ |
| `labeled_amount_total` | numeric | — | — | ✓ |

---

## 5. Gold layer — display-ready projection

**Principle**: flatten silver JSONB into typed columns; denormalize party names / countries / risk tiers / bank names onto entity rows so the API never has to touch silver. One publisher (`src/gold/publish.py`) handles all typologies uniformly.

### `gold.finding`

Flattened finding header (188 rows).

| Column | Type | Source (silver) |
|---|---|---|
| `finding_id` | `BIGINT PRIMARY KEY` | `silver.finding.finding_id` |
| `assessment_id` | `TEXT NOT NULL` | direct |
| `finding_type` | `TEXT NOT NULL` | direct |
| `severity` | `TEXT NOT NULL` | direct |
| `title` | `TEXT NOT NULL` | direct |
| `description` | `TEXT` | direct |
| `detected_at` | `TIMESTAMP NOT NULL` | direct |
| `hop_count` | `SMALLINT` | `summary_stats->>'hops'` (null for non-circular) |
| `currency` | `TEXT` | `summary_stats->>'currency'` |
| `amount_min` | `NUMERIC(20,4)` | `summary_stats->>'amount_min'` |
| `amount_max` | `NUMERIC(20,4)` | `summary_stats->>'amount_max'` |
| `amount_ratio` | `NUMERIC(10,4)` | `summary_stats->>'amount_ratio'` (null for non-circular) |
| `time_span_hours` | `INTEGER` | `summary_stats->>'time_span_hours'` |
| `control_bsa` | `TEXT` | `control_mapping->>'BSA'` |
| `control_fatf` | `TEXT` | `control_mapping->>'FATF'` |
| `control_eu_amld` | `TEXT` | `control_mapping->>'EU_AMLD'` |
| `sla_trigger_date` | `TIMESTAMP` | direct |
| `sla_due_date` | `TIMESTAMP` | `sla_trigger_date + sla_duration` (computed) |
| `sla_duration` | `INTERVAL` | direct |
| `party_count` | `INTEGER` | computed — distinct Party entities |
| `bank_count` | `INTEGER` | computed — distinct FI entities |
| `country_count` | `INTEGER` | computed — distinct party countries |
| `countries` | `TEXT[]` | array of country codes |
| `banks` | `TEXT[]` | array of bank display names |

### `gold.finding_entity`

Denormalized entity rows — display name, country, risk tier, bank name prejoined.

| Column | Type | Notes |
|---|---|---|
| `finding_id` | `BIGINT` FK | |
| `entity_type` | `TEXT` | Account / Party / FinancialInstitution |
| `entity_id` | `TEXT` | |
| `role` | `TEXT` | |
| `display_name` | `TEXT` | party `name`, bank `name`, or `account_key` |
| `country` | `TEXT` | Party only |
| `risk_tier` | `TEXT` | Party only |
| `bank_id` | `TEXT` | Account only |
| `bank_name` | `TEXT` | Account + FinancialInstitution |
| `owner_party_id` | `TEXT` | Account only — its `PRIMARY_OWNER` party (on `feat/ui` branch only) |
| PK | `(finding_id, entity_type, entity_id)` | |

### `gold.finding_edge`

Flattened edges (typed columns instead of JSONB).

| Column | Type | Notes |
|---|---|---|
| `finding_id` | `BIGINT` FK | |
| `hop_order` | `SMALLINT` | |
| `edge_type` | `TEXT` | `transfers_to` |
| `from_account_key` | `TEXT` | |
| `to_account_key` | `TEXT` | |
| `from_bank_id` | `TEXT` | denormalized from `silver.account` |
| `to_bank_id` | `TEXT` | |
| `fin_txn_id` | `BIGINT` | |
| `amount` | `NUMERIC(20,4)` | |
| `currency` | `TEXT` | |
| `event_timestamp` | `TIMESTAMP` | |
| `payment_format` | `TEXT` | |
| PK | `(finding_id, hop_order)` | |

---

## 6. Data flow — how bronze rows become a finding

Tracing the hero ring (finding 81) through the layers:

```
bronze.transactions_raw         (3 rows — IsLaundering=1)
                                        │
                      silver.transform  │  DISTINCT, ROW_NUMBER, FK joins
                                        ▼
silver.financial_institution    ('0121','0222','0223')
silver.account                  (3 account rows)
silver.party                    (CUST513652, CUST222925, CUST256335 — from KYC)
silver.financial_transaction    (fin_txn_id 2521343, 3934906, 4064891)
silver.has_account              (3 PRIMARY_OWNER edges)
silver.is_held_at               (3 account→bank edges)
silver.has_originating_account  (3 rows)
silver.has_beneficiary_account  (3 rows)
silver.transfers_to             (3 rows — the KG's cycle-ready edges)
                                        │
                circular_flow detector  │  3-way self-join over transfers_to
                                        ▼
silver.finding                  (finding_id=81, CIRCULAR_FLOW, HIGH)
silver.finding_entity           (9 rows: 3 accounts + 3 parties + 3 FIs)
silver.finding_edge             (3 rows — hop_order 1..3, cites fin_txn_ids)
                                        │
                      gold.publish      │  JSONB → typed columns; party/bank joins
                                        ▼
gold.finding                    (1 row — amount_max, countries[], bank pills…)
gold.finding_entity             (9 rows — names, flags, bank names prejoined)
gold.finding_edge               (3 rows — from_bank_id, to_bank_id, payment_format)
                                        │
                       FastAPI / UI     │
                                        ▼
   GET /findings  ← gold.finding
   GET /findings/81  ← gold.finding
   GET /findings/81/graph  ← gold.finding_entity + gold.finding_edge
```

---

## 7. Key invariants & rules

- **Layer isolation**: `silver.*` joins `bronze.*` only inside the labeled-exposure detector (by design — it's the supervised signal). Everything else is layer-pure: silver transforms from bronze, gold publishes from silver, API reads gold.
- **`bronze.is_laundering` is label-only.** Graph-native detectors (`circular_flow`, `mule_hub`) must not read it. `laundering_exposure` reads it openly as the contrast case.
- **`fin_txn_id` is deterministic.** Assigned by `ROW_NUMBER()` over bronze with fixed ordering; the same bronze re-load produces the same IDs. Findings cite these IDs for provenance.
- **Idempotent pipeline**: every module TRUNCATEs its own outputs before re-inserting. Safe to re-run any step.
- **Assessment decoupling**: adding a new typology means (a) seeding a new `silver.assessment_config` row and (b) writing a detector that writes to `silver.finding*`. No gold schema change, no API change, no UI change (beyond label copy).

---

## 8. Row-count reference (current state)

| Table | Rows |
|---|---|
| `bronze.transactions_raw` | 5,078,345 |
| `bronze.kyc_customers_raw` | 515,088 |
| `bronze.account_customer_link_raw` | 515,088 |
| `silver.party` | 515,088 |
| `silver.financial_institution` | ~800 (distinct banks) |
| `silver.account` | 515,088 |
| `silver.financial_transaction` | 5,078,345 |
| `silver.has_account` | 515,088 |
| `silver.is_held_at` | 515,088 |
| `silver.has_originating_account` | 5,078,345 |
| `silver.has_beneficiary_account` | 5,078,345 |
| `silver.transfers_to` | 5,078,345 |
| `silver.assessment_config` | 3 |
| `silver.finding` | 188 (109 circular + 40 mule + 39 exposure) |
| `silver.finding_entity` | ~1,728 |
| `silver.finding_edge` | ~1,079 |
| `gold.finding` | 188 |
| `gold.finding_entity` | ~1,728 |
| `gold.finding_edge` | ~1,079 |

---

## 9. Where the schemas live

| Layer | DDL file | Python module |
|---|---|---|
| Bronze | `repo/schema/001_init.sql` | `repo/src/bronze/load.py` |
| Silver KG | `repo/schema/002_silver.sql` | `repo/src/silver/transform.py` |
| Silver findings | `repo/schema/003_silver_findings.sql` | `repo/src/assessments/{circular_flow,mule_hub,laundering_exposure}.py` |
| Gold | `repo/schema/004_gold.sql` | `repo/src/gold/publish.py` |

All DDL files are mounted into Postgres on `docker compose up -d` first boot; detectors also re-apply the DDL idempotently (`CREATE TABLE IF NOT EXISTS` + `ON CONFLICT DO UPDATE`) on every run so the pipeline self-heals.

---

## 10. Design references

- `docs/kg-model.md` — the FIBO-aligned KG model (full source-of-truth for node/edge types and attributes).
- `docs/architecture.md` — pipeline diagram and component map.
- `notes/reference-alignment.md` — how the silver findings / assessment_config / control_mapping / SLA shape mirrors `sds-product-em`.
- `notes/decisions.md` — design decisions with rationale (newest at top).
