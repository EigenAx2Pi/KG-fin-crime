# KG-fin-crime

Knowledge graph for financial crime — the PAI Hackathon 2026 project. Ports the Prevalent SDS medallion pipeline from cybersecurity exposure management to financial crime to demonstrate the platform is domain-agnostic.

## Status

**Pipeline + three assessments + API are complete and on `main`. UI is the last-mile and is not in this branch — see [§ Building the UI](#building-the-ui).**

### Backwards build progress

| # | Step | State |
|---|------|-------|
| 7 | CSV + ring exist | ✅ Real AMLSim; hero ring verified in `scripts/find_cycles.py` |
| 6 | Bronze loaded | ✅ 5.08M txns / 515k KYC / 515k links via `src/bronze/load.py` |
| 5 | Silver entities + edges | ✅ 9 tables populated via `src/silver/transform.py` (~15 min run) |
| 4 | Silver assessments | ✅ **188 findings** across 3 typologies (all writing to the same `silver.finding*` tables, keyed by `assessment_id`): <br>• `circular_flow_v1` — 109 rings (32 HIGH / 77 MEDIUM) via `src/assessments/circular_flow.py`. Graph-native, unsupervised. Hero ring surfaces as finding 81, HIGH. <br>• `mule_hub_v1` — 40 fan-in/fan-out hubs (9 CRITICAL / 5 HIGH / 26 MEDIUM) via `src/assessments/mule_hub.py`. Graph-native, unsupervised. <br>• `laundering_exposure_v1` — 39 label-exposed accounts (4 CRITICAL / 7 HIGH / 28 MEDIUM) via `src/assessments/laundering_exposure.py`. Supervised — reads `bronze.is_laundering`. |
| 3 | Gold publisher | ✅ `gold.finding` (188) / `gold.finding_entity` (1,728) / `gold.finding_edge` (1,079) via `src/gold/publish.py` (<1s). Flattened summary_stats + control_mapping; party / bank / country denormalized onto entity rows. Typology-agnostic — same publisher handles all assessments. |
| 2 | FastAPI | ✅ `src/api/` — `GET /findings`, `/findings/{id}`, `/findings/{id}/graph`, `/healthz`. Serves `gold.*` only. |
| 1 | UI renders finding | 🚧 **To be built.** See [`docs/api.md`](docs/api.md) and [`docs/data-model.md`](docs/data-model.md). A reference implementation exists on `feat/ui` — crib from `ui/src/components/RingGraph.tsx` if useful. |

### Resume commands (everything already populated)

```bash
cd repo/
docker compose up -d               # Postgres 16
source .venv/bin/activate          # or rebuild: python3 -m venv .venv && pip install -e .
uvicorn api.main:app --reload      # FastAPI on http://127.0.0.1:8000 (docs at /docs)
```

Verify all layers are populated:

```bash
docker compose exec postgres psql -U kgfc -d kgfincrime -c "
  SELECT 'bronze.transactions_raw'      AS t, count(*) FROM bronze.transactions_raw
  UNION ALL SELECT 'silver.transfers_to',           count(*) FROM silver.transfers_to
  UNION ALL SELECT 'silver.party',                  count(*) FROM silver.party
  UNION ALL SELECT 'silver.account',                count(*) FROM silver.account
  UNION ALL SELECT 'silver.finding',                count(*) FROM silver.finding
  UNION ALL SELECT 'gold.finding',                  count(*) FROM gold.finding
  UNION ALL SELECT 'gold.finding_entity',           count(*) FROM gold.finding_entity
  UNION ALL SELECT 'gold.finding_edge',             count(*) FROM gold.finding_edge;"
# Expect: 5,078,345 / 5,078,345 / 515,088 / 515,088 / 188 / 188 / 1,728 / 1,079
```

Breakdown by typology:

```bash
docker compose exec postgres psql -U kgfc -d kgfincrime -c "
  SELECT finding_type, severity, count(*)
  FROM silver.finding
  GROUP BY finding_type, severity
  ORDER BY finding_type, severity;"
# CIRCULAR_FLOW       HIGH/MEDIUM            32 / 77
# LAUNDERING_EXPOSURE CRITICAL/HIGH/MEDIUM    4 /  7 / 28
# MULE_HUB            CRITICAL/HIGH/MEDIUM    9 /  5 / 26
```

### Cold start (nothing running yet)

```bash
cd repo/
cp .env.example .env
docker compose up -d               # first boot applies schema/*.sql automatically
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m bronze.load                     # ~25s
python -m silver.transform                # ~15 min (per-row FK checks, one-time cost)
python -m assessments.circular_flow       # ~4 min (graph-native, unsupervised — 3-way self-join on 5M edges)
python -m assessments.mule_hub            # ~30s  (graph-native, unsupervised — fan-in/fan-out GROUP BY)
python -m assessments.laundering_exposure # ~2s   (supervised — joins silver.transfers_to to bronze IsLaundering=1)
python -m gold.publish                    # <1s   (188 rows — flatten + denormalize)
uvicorn api.main:app --reload             # FastAPI on http://127.0.0.1:8000
```

To rebuild from a clean slate: `docker compose down -v` wipes the volume and all data, then re-run the cold-start sequence.

### API surface

```
GET /healthz                        → liveness probe
GET /findings?severity=&limit=      → list view (sorted CRITICAL→LOW, then detected_at DESC)
GET /findings/{id}                  → full detail (control_mapping + SLA + amount_ratio)
GET /findings/{id}/graph            → {entities:[...], edges:[...]} for the drill-down view
```

Hero-ring smoke test: `curl localhost:8000/findings/81/graph` → 9 entities (3 accounts, 3 banks, 3 parties with names/countries/risk tiers) + 3 edges.

Full API spec with TypeScript types and sample payloads: [`docs/api.md`](docs/api.md).

Full data-model reference (every table, every column, the FIBO-aligned KG): [`docs/data-model.md`](docs/data-model.md).

### Detector validation

Hero ring surfaces as `silver.finding` row with severity `HIGH`:

| Hop | From | To | Amount | Date | fin_txn_id |
|---|---|---|---|---|---|
| 1 | `0223:8119F8CC0` (Ava Miller / NL / MEDIUM) | `0222:811D80C30` (Mia Patel / GB / LOW) | 56,544.74 SAR ACH | 2022-09-05 11:21 | 2,521,343 |
| 2 | `0222:811D80C30` | `0121:8000E1590` (Lucas de Vries / AE / LOW) | 51,178.80 SAR ACH | 2022-09-08 09:41 | 3,934,906 |
| 3 | `0121:8000E1590` | `0223:8119F8CC0` | 51,203.66 SAR ACH | 2022-09-08 16:19 | 4,064,891 |

Pillar-1 label-overlap check (the circular-flow detector does NOT read `bronze.is_laundering`; the label is used only post-hoc):

```bash
docker compose exec postgres psql -U kgfc -d kgfincrime -c "
  WITH edge_label AS (
    SELECT fe.finding_id, fe.hop_order, b.is_laundering
    FROM silver.finding_edge fe
    JOIN silver.transfers_to t        ON t.fin_txn_id = fe.fin_txn_id
    JOIN bronze.transactions_raw b
      ON b.event_timestamp                        = t.event_timestamp
     AND (b.from_bank || ':' || b.from_account)   = t.from_account_key
     AND (b.to_bank   || ':' || b.to_account)     = t.to_account_key
     AND b.amount_paid                            = t.amount
  ),
  per_finding AS (
    SELECT finding_id, SUM(is_laundering) AS hops_labeled FROM edge_label GROUP BY finding_id
  )
  SELECT count(*) FILTER (WHERE hops_labeled=3) AS all_labeled,
         count(*) FILTER (WHERE hops_labeled>=1) AS any_labeled,
         count(*) AS total
  FROM per_finding
  WHERE finding_id IN (SELECT finding_id FROM silver.finding WHERE assessment_id='circular_flow_v1');"
# Expect: 87 / 91 / 109 (~80% fully label-perfect; ~83% touch at least one laundering-flagged edge)
```

## Building the UI

The UI is the one step not shipped on `main`. Everything you need to build it is already here:

- [`docs/api.md`](docs/api.md) — API spec with TypeScript types for `FindingSummary`, `FindingDetail`, `GraphEntity`, `GraphEdge`, `FindingGraph`; sample `curl` calls against three hand-picked finding IDs; CORS and run instructions; field-level UI guidance.
- [`docs/data-model.md`](docs/data-model.md) — every table and column from bronze through gold; the FIBO-aligned entity/edge graph; the per-typology `summary_stats` JSONB matrix; invariants that matter when rendering findings.
- [`../demo/hero-moment.md`](../demo/hero-moment.md) — the 30-second demo the UI exists to serve. Every UI decision should be tested against it.

### Recommended scope

Two screens carry the hero moment:

1. **Findings list** — cards or rows over `/findings?severity=...&limit=...`. Severity pill, title, `amount_max` + currency, country flags + codes, bank_count / party_count.
2. **Finding detail** — split pane.
   - Left: fields from `/findings/{id}` (severity, title, description, control-mapping pills, SLA dates, parties with flag + country + risk tier).
   - Right: graph rendered from `/findings/{id}/graph`. Cytoscape.js with `cose-bilkent` layout works well; nodes styled by `entity_type`, edges colored by `edge_type`.

### Reference implementation on `feat/ui`

A working reference UI exists at `git checkout feat/ui` — Vite + React + TypeScript + Tailwind v4 + Cytoscape.js, dark glass theme, pipeline framing header, animated ring graph. Structure and styles are reasonable to lift. Key files:

- `ui/src/lib/types.ts` — TS types mirroring the pydantic API models.
- `ui/src/lib/api.ts` — fetch wrapper with `/api` Vite proxy.
- `ui/src/components/RingGraph.tsx` — Cytoscape configuration with three edge types (cycle, hasAccount, isHeldAt).
- `ui/src/components/FindingDetailPane.tsx` — the two-column detail layout.
- `ui/src/components/FindingsList.tsx` — filterable left pane.
- `ui/vite.config.ts` — `@` path alias + `/api` → `http://127.0.0.1:8000` proxy.

`feat/ui` also adds an `owner_party_id` column on `gold.finding_entity` (populated for Account rows from `silver.has_account`) so the UI can draw party→account edges. If you want this on `main`, it's a ~10-line cherry-pick: `schema/004_gold.sql` gets the column, `src/gold/publish.py` gets a LATERAL join in the entity insert, `src/api/models.py` + `src/api/routes/findings.py` expose it.

### Anti-goals (flagged in `demo/hero-moment.md`)

- No auth, routing polish, or theming wars. Every hour on UI gloss is an hour not rehearsing the 30-second demo.
- No tooltips explaining what the judge is seeing. If the finding needs narration, fix the finding, not the tooltip.
- No reference-repo modifications.

## Repository layout

```
repo/
├── docs/
│   ├── api.md              → REST spec + TypeScript types + sample payloads
│   └── data-model.md       → Every table across bronze/silver/gold + invariants
├── schema/
│   ├── 001_init.sql        → bronze.*
│   ├── 002_silver.sql      → silver KG (4 node types + 5 edge types)
│   ├── 003_silver_findings.sql → silver.assessment_config + silver.finding*
│   └── 004_gold.sql        → gold.finding / finding_entity / finding_edge
├── src/
│   ├── common/db.py        → psycopg connection helper
│   ├── bronze/load.py      → CSV → bronze.*
│   ├── silver/transform.py → bronze.* → silver.* (KG nodes + edges)
│   ├── assessments/
│   │   ├── circular_flow.py        → 3-hop cycle detector (graph-native)
│   │   ├── mule_hub.py             → fan-in/fan-out detector (graph-native)
│   │   └── laundering_exposure.py  → label-driven detector (supervised)
│   └── gold/publish.py     → silver.finding* → gold.*
├── docker-compose.yml      → Postgres 16 with schema/*.sql auto-applied on first boot
├── pyproject.toml          → psycopg[binary,pool], fastapi, uvicorn
└── README.md               → this file
```

## Where the broader workspace is

This repo is the implementation target. The enclosing workspace at `/home/nikhil/Hackathon/` (or wherever you copied it) has context the repo itself doesn't carry:

- `../CLAUDE.md` — workspace rules + pickup order for new sessions.
- `../notes/decisions.md` — non-trivial design decisions with rationale (newest at top).
- `../notes/reference-alignment.md` — how the build compares to the Prevalent SDS reference platform.
- `../docs/problem-statement.md` — what the submission is claiming.
- `../docs/architecture.md` — the simplified CSV → Postgres → Python pipeline.
- `../docs/judging-criteria.md` — the hackathon's two pillars.
- `../demo/hero-moment.md` — the 30-second demo scope everything is built around.
- `../reference-repos/CONTEXT.md` — index of the 10 reference repos that make up the SDS platform.

## Stack

CSV (bronze) → PostgreSQL (silver + gold, one DB, schemas per layer) → Python (pandas + SQL) → FastAPI → UI (TBD). No Spark, no Iceberg, no NiFi — scaled for low demo data volume. See `../notes/decisions.md` (2026-04-23 stack simplification) for rationale.

## Upstream

<https://github.com/NIKHIL-523/KG-fin-crime>
