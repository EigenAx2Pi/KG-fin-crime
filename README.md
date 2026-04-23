# KG-fin-crime

Knowledge graph for financial crime — the PAI Hackathon 2026 project. Ports the Prevalent SDS medallion pipeline from cybersecurity exposure management to financial crime to demonstrate the platform is domain-agnostic.

## Status

**Bronze + silver complete. Circular-flow assessment is next (step 4 of the backwards build).**

### Backwards build progress

| # | Step | State |
|---|------|-------|
| 7 | CSV + ring exist | ✅ Real AMLSim; hero ring verified in `scripts/find_cycles.py` |
| 6 | Bronze loaded | ✅ 5.08M txns / 515k KYC / 515k links via `src/bronze/load.py` |
| 5 | Silver entities + edges | ✅ 9 tables populated via `src/silver/transform.py` (~15 min run) |
| 4 | Silver assessment (circular-flow detector) | ⏳ **Next** |
| 3 | Gold publisher | ⏳ |
| 2 | FastAPI | ⏳ |
| 1 | UI renders finding | ⏳ |

### Resume commands

```bash
cd repo/
docker compose up -d               # Postgres 16 (auto-applies schema/*.sql on first boot only)
source .venv/bin/activate          # or rebuild: python3 -m venv .venv && pip install -e .
```

Verify bronze + silver are populated:

```bash
docker compose exec postgres psql -U kgfc -d kgfincrime -c "
  SELECT 'bronze.transactions_raw'      AS t, count(*) FROM bronze.transactions_raw
  UNION ALL SELECT 'silver.transfers_to',           count(*) FROM silver.transfers_to
  UNION ALL SELECT 'silver.party',                  count(*) FROM silver.party
  UNION ALL SELECT 'silver.account',                count(*) FROM silver.account;"
# Expect: 5,078,345 / 5,078,345 / 515,088 / 515,088
```

Confirm the hero ring is in silver:

```bash
docker compose exec postgres psql -U kgfc -d kgfincrime -c "
  SELECT event_timestamp, from_account_key || ' -> ' || to_account_key AS hop, amount, currency, payment_format
  FROM silver.transfers_to
  WHERE (from_account_key, to_account_key) IN (
    ('0223:8119F8CC0','0222:811D80C30'),
    ('0222:811D80C30','0121:8000E1590'),
    ('0121:8000E1590','0223:8119F8CC0'))
  ORDER BY event_timestamp;"
```

### Cold start (nothing running yet)

```bash
cd repo/
cp .env.example .env
docker compose up -d               # First boot applies schema/*.sql automatically
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m bronze.load              # ~25s
python -m silver.transform         # ~15 min (FK checks are per-row; one-time cost)
```

To rebuild from a clean slate: `docker compose down -v` wipes the volume and all data, then re-run the cold-start sequence.

### Next session: step 4 — circular-flow assessment

**Goal.** Produce `silver.finding` rows that surface the laundering ring(s) by graph traversal alone — no peeking at `is_laundering`.

> **Before writing the DDL, read `../notes/reference-alignment.md`.** It calls out three EM-shape additions (persisted `assessment_config`, regulatory `control_mapping`, SLA columns) that cost ~50 lines total and meaningfully tighten the pillar-1 narrative. Fold them in here, not later.

1. **DDL — `schema/003_silver_findings.sql`**: three core tables following the `sds-product-em` finding shape (plus `assessment_config` per the reference-alignment note)
   - `silver.assessment_config` (assessment_id PK, scope_query, success_condition, finding_config JSONB, control_mapping JSONB, sla_duration) — seed with `circular_flow_v1`
   - `silver.finding` (finding_id PK, assessment_id FK, finding_type, severity, title, description, detected_at, summary_stats JSONB, **control_mapping JSONB**, **sla_trigger_date / sla_action_date / sla_duration**)
   - `silver.finding_entity` (finding_id, entity_type, entity_id, role) — Account / Party / FinancialInstitution references
   - `silver.finding_edge` (finding_id, edge_type, from_entity, to_entity, fin_txn_id, hop_order, attrs JSONB)

2. **Detector — `src/assessments/circular_flow.py`**: single recursive-CTE over `silver.transfers_to`, finds 3-hop cycles subject to:
   - **Distinct accounts** (A → B → C → A, A ≠ B ≠ C)
   - **Time window** ≤ 14 days
   - **Amount ratio** `max/min ≤ 1.5`
   - **Same currency** across all 3 hops
   - **Min amount** > 1,000 (filter dust)

3. **Severity rule**: `HIGH` if all 3 hops same `payment_format` and amount spread ≤ 20%; `MEDIUM` otherwise. Hero ring → `HIGH` (51k/51k/56k SAR, all ACH).

4. **Validation**: 45 distinct 3-cycles exist in the `is_laundering=1` subset (per `scripts/find_cycles.py`). Post-run, spot-check how many the detector surfaces — that's the Pillar-1 "detector works" evidence.

5. **Rule** (see `notes/decisions.md` 2026-04-23): detector **must not read** `bronze.is_laundering`. Keep ground truth for post-hoc validation only.

**Hero ring for quick-check after detector runs:**

| Hop | From | To | Amount | Date | fin_txn_id |
|---|---|---|---|---|---|
| 1 | `0223:8119F8CC0` (Ava Miller / NL / MEDIUM) | `0222:811D80C30` (Mia Patel / GB / LOW) | 56,544.74 SAR ACH | 2022-09-05 11:21 | 2,521,343 |
| 2 | `0222:811D80C30` | `0121:8000E1590` (Lucas de Vries / AE / LOW) | 51,178.80 SAR ACH | 2022-09-08 09:41 | 3,934,906 |
| 3 | `0121:8000E1590` | `0223:8119F8CC0` | 51,203.66 SAR ACH | 2022-09-08 16:19 | 4,064,891 |

## Where to look

This repo is the implementation target. The full workspace lives one level up at `/home/nikhil/Hackathon/` — that is where docs, notes, design, reference material, and demo assets live. **Start there, not here**, when onboarding:

- `../CLAUDE.md` — workspace rules + pickup order.
- `../notes/decisions.md` — current direction (newest at top).
- `../docs/problem-statement.md` — what we're solving.
- `../demo/hero-moment.md` — the 30-second demo we're building backwards from.
- `../docs/architecture.md` — the simplified CSV → Postgres → Python pipeline.
- `../reference-repos/CONTEXT.md` — the Prevalent SDS platform we're porting patterns from.

## Planned layout (once code lands)

```
repo/
├── schema/           DDL for bronze.* / silver.* / gold.*
├── src/
│   ├── bronze/       CSV → Postgres loaders
│   ├── silver/       Normalization → entities + relationships
│   ├── assessments/  Graph traversal → candidate findings (e.g. circular_flow.py)
│   └── gold/         Publishers shaping findings for the UI
├── data/             Symlink or copy of ../data/ (curated CSVs)
└── README.md         This file
```

## Stack

CSV (bronze) → PostgreSQL (silver + gold, one DB, schemas per layer) → Python (pandas + SQL, optional `networkx` for graph traversal). No Spark, no Iceberg, no NiFi — scaled for low demo data volume. See `../notes/decisions.md` (2026-04-23 stack simplification) for rationale.

## Upstream

<https://github.com/NIKHIL-523/KG-fin-crime> — empty on GitHub at clone time; this is the first commit target.
