# KG-fin-crime — project context

Knowledge graph for financial crime. Originally PAI Hackathon 2026; being repolished into a portfolio piece. Lives under `mindforge/` until graduated.

## What this is

Medallion pipeline (Postgres bronze → silver → gold) over IBM AMLSim HI-Small, three detectors, FastAPI + React/Vite/Cytoscape dashboard. See `README.md` for the public-facing pitch and `docs/build-log.md` for the hackathon-era process artifact.

## Working notes

- **Single Postgres instance.** No Neo4j, no AGE. The "knowledge graph" is SQL tables with typed edge tables and FIBO-aligned naming. Detectors are SQL with self-joins and `LATERAL` joins.
- **Discipline boundary:** `circular_flow` and `mule_hub` must not read `bronze.is_laundering`. `laundering_exposure` is the only detector that does. If you add a graph-native detector, do not introduce a label dependency — the label-overlap evidence in `docs/build-log.md` is the Pillar-1 story.
- **Finding schema is typology-agnostic.** New detectors go in `src/assessments/<name>.py`, write to `silver.finding*` keyed by `assessment_id`, and the existing `gold/publish.py` will pick them up without changes.
- **AMLSim data is not in the repo.** Place `HI-Small_*.csv` in `../data/` (default; override with `DATA_DIR=` env).
- **`make demo` is the cold-start path.** ~22 min from clone to populated database.

## Code conventions

- Python 3.10+. `psycopg[binary,pool]` (psycopg3), not psycopg2.
- Bronze loads use `COPY FROM STDIN`, not `INSERT`. Pandas is used for the first parse only.
- All assessments share the same `silver.finding*` shape — don't fork the table layout for a new typology.
- API serves `gold.*` exclusively. Silver is internal.
- UI uses `@/...` path alias (see `ui/vite.config.ts`) and proxies `/api` to `127.0.0.1:8000`.

## Portfolio-polish status (2026-05-14)

What changed in this session (away from the hackathon framing):

- React UI from `feat/ui` brought onto `main`. The old standalone `ui/index.html` (921-line single-file demo) was replaced.
- `owner_party_id` schema/code change brought across so `GraphEntity.owner_party_id` is populated (`schema/004_gold.sql`, `src/gold/publish.py`, `src/api/models.py`, `src/api/routes/findings.py`).
- README rewritten for portfolio framing — leads with technical substance, not hackathon framing.
- Build-log moved out of README into `docs/build-log.md`.
- `Makefile` added — `make demo` is the one-command cold start.

What's still pending for portfolio-grade (see `STATUS.md`).

## Things to not do here

- **Don't add tests just because.** The mindforge default is "no tests unless asked". If the project gets a small `pytest` suite, it's a deliberate portfolio signal — discuss before adding.
- **Don't introduce auth, deployment yaml, or framework gloss** — those are stage-3 polish (tier 3 in the polish plan) and not in scope right now.
- **Don't read `bronze.is_laundering` from graph-native detectors.** That's the whole point of the Pillar-1 story.

## Dataset note (2026-05-24)

IBM consolidated the AMLSim Kaggle dataset in July 2025: the legacy 3-file layout (`HI-Small_Trans.csv` + `HI-Small_KYC_Customers.csv` + `HI-Small_Account_Customer_Link.csv`) was replaced by a 2-file layout (`HI-Small_Trans.csv` + `HI-Small_accounts.csv`). The bronze loader, schema, and silver transform were rewritten on this date to match the new layout. Notable consequence: `HI-Small_accounts.csv` and `HI-Small_Trans.csv` no longer share an account-key namespace, so `silver.has_account` joins do not light up `silver.party` ownership for any transaction account. UI panels for party / country / risk render blank. Detector results are unaffected (they read `silver.transfers_to` only). See README §"What's real, what's synthetic" for the full disclosure.

## Graduation criteria for this project

Per `~/repo/playfield/CLAUDE.md`:
1. ✅ Clear one-sentence purpose statement (README opener).
2. ✅ `README.md` with run instructions (`make demo`).
3. ✅ No hardcoded secrets — Postgres creds are dev defaults in `docker-compose.yml`, app reads `.env`.
4. ✅ Happy path works end-to-end — `make demo` cold-start verified 2026-05-24, 188 findings produced (109 circular + 40 mule + 39 LX), pipeline completes in ~6 min on Postgres 16.
