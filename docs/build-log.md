# Build log

Process artifact from the original PAI Hackathon 2026 build. Kept here rather than the README because it documents *how* the pipeline was built (backwards-from-the-demo, validation queries, hero ring), not how to use it. Useful as a reference for the validation patterns; not useful as a landing page.

## Backwards build progress

The build was sequenced backwards from the demo — starting with "what does the UI render?" and working back toward the CSV. Each step's exit criteria was a runnable check.

| # | Step | Exit check |
|---|------|------------|
| 7 | CSV + ring exist | Real AMLSim ingested; hero ring exists in raw data. |
| 6 | Bronze loaded | 5,078,345 txns / 515,088 KYC / 515,088 account-customer links via `src/bronze/load.py`. |
| 5 | Silver entities + edges | 9 tables populated via `src/silver/transform.py` (~15 min run). |
| 4 | Silver assessments | **188 findings** across 3 typologies (all writing to the same `silver.finding*` tables, keyed by `assessment_id`): <br>• `circular_flow_v1` — 109 rings (32 HIGH / 77 MEDIUM). Graph-native, unsupervised. Hero ring surfaces as finding 81, HIGH. <br>• `mule_hub_v1` — 40 fan-in/fan-out hubs (9 CRITICAL / 5 HIGH / 26 MEDIUM). Graph-native, unsupervised. <br>• `laundering_exposure_v1` — 39 label-exposed accounts (4 CRITICAL / 7 HIGH / 28 MEDIUM). Supervised — reads `bronze.is_laundering`. |
| 3 | Gold publisher | `gold.finding` (188) / `gold.finding_entity` (1,728) / `gold.finding_edge` (1,079) via `src/gold/publish.py` (<1s). |
| 2 | FastAPI | `GET /findings`, `/findings/{id}`, `/findings/{id}/graph`, `/healthz`. Serves `gold.*` only. |
| 1 | UI renders finding | Two-pane React dashboard — findings list + ring-graph detail. |

## Verification queries

### All layers populated

```sql
SELECT 'bronze.transactions_raw' AS t, count(*) FROM bronze.transactions_raw
UNION ALL SELECT 'silver.transfers_to', count(*) FROM silver.transfers_to
UNION ALL SELECT 'silver.party', count(*) FROM silver.party
UNION ALL SELECT 'silver.account', count(*) FROM silver.account
UNION ALL SELECT 'silver.finding', count(*) FROM silver.finding
UNION ALL SELECT 'gold.finding', count(*) FROM gold.finding
UNION ALL SELECT 'gold.finding_entity', count(*) FROM gold.finding_entity
UNION ALL SELECT 'gold.finding_edge', count(*) FROM gold.finding_edge;
-- Expect: 5,078,345 / 5,078,345 / 515,088 / 515,088 / 188 / 188 / 1,728 / 1,079
```

### Breakdown by typology

```sql
SELECT finding_type, severity, count(*)
FROM silver.finding
GROUP BY finding_type, severity
ORDER BY finding_type, severity;
-- CIRCULAR_FLOW       HIGH/MEDIUM            32 / 77
-- LAUNDERING_EXPOSURE CRITICAL/HIGH/MEDIUM    4 /  7 / 28
-- MULE_HUB            CRITICAL/HIGH/MEDIUM    9 /  5 / 26
```

## Hero ring

Hero ring surfaces as `silver.finding` row with severity `HIGH`:

| Hop | From | To | Amount | Date | fin_txn_id |
|---|---|---|---|---|---|
| 1 | `0223:8119F8CC0` (Ava Miller / NL / MEDIUM) | `0222:811D80C30` (Mia Patel / GB / LOW) | 56,544.74 SAR ACH | 2022-09-05 11:21 | 2,521,343 |
| 2 | `0222:811D80C30` | `0121:8000E1590` (Lucas de Vries / AE / LOW) | 51,178.80 SAR ACH | 2022-09-08 09:41 | 3,934,906 |
| 3 | `0121:8000E1590` | `0223:8119F8CC0` | 51,203.66 SAR ACH | 2022-09-08 16:19 | 4,064,891 |

Smoke test:

```bash
curl localhost:8000/findings/81/graph
# → 9 entities (3 accounts, 3 banks, 3 parties with names/countries/risk tiers) + 3 edges
```

## Label-overlap check (Pillar 1 evidence)

The circular-flow detector does **not** read `bronze.is_laundering`. The label is used only post-hoc to measure structure-vs-label agreement.

```sql
WITH edge_label AS (
  SELECT fe.finding_id, fe.hop_order, b.is_laundering
  FROM silver.finding_edge fe
  JOIN silver.transfers_to t ON t.fin_txn_id = fe.fin_txn_id
  JOIN bronze.transactions_raw b
    ON b.event_timestamp                      = t.event_timestamp
   AND (b.from_bank || ':' || b.from_account) = t.from_account_key
   AND (b.to_bank   || ':' || b.to_account)   = t.to_account_key
   AND b.amount_paid                          = t.amount
),
per_finding AS (
  SELECT finding_id, SUM(is_laundering) AS hops_labeled FROM edge_label GROUP BY finding_id
)
SELECT count(*) FILTER (WHERE hops_labeled=3) AS all_labeled,
       count(*) FILTER (WHERE hops_labeled>=1) AS any_labeled,
       count(*) AS total
FROM per_finding
WHERE finding_id IN (SELECT finding_id FROM silver.finding WHERE assessment_id='circular_flow_v1');
-- Expect: 87 / 91 / 109 (~80% fully label-perfect; ~83% touch at least one laundering-flagged edge)
```

## Cold-start sequence

For reference — what `make demo` runs:

```bash
docker compose up -d                       # Postgres 16 — first boot applies schema/*.sql
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m bronze.load                      # ~25s
python -m silver.transform                 # ~15 min (per-row FK checks, one-time cost)
python -m assessments.circular_flow        # ~4 min  (3-way self-join on 5M edges)
python -m assessments.mule_hub             # ~30s    (fan-in/fan-out GROUP BY)
python -m assessments.laundering_exposure  # ~2s     (joins to bronze.is_laundering)
python -m gold.publish                     # <1s     (188 rows — flatten + denormalize)
uvicorn api.main:app --reload              # http://127.0.0.1:8000
```
