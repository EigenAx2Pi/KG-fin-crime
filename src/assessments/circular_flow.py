"""Circular-flow detector — 3-hop laundering ring assessment.

Run from repo/:
    python -m assessments.circular_flow

Finds directed cycles A -> B -> C -> A over silver.transfers_to with:
  - 3 distinct accounts
  - chronological hops within a 14-day window
  - single currency across all 3 hops
  - max(amount) / min(amount) <= 1.5
  - min(amount) > 1000 (filter dust)

Writes one row per cycle to silver.finding, with related entities/edges for
drill-down. Severity is HIGH if all 3 hops share payment_format AND amount
spread <= 20%, MEDIUM otherwise.

Rule: this detector MUST NOT read bronze.is_laundering — the label is reserved
for post-hoc validation (see notes/decisions.md 2026-04-23 "Demo ring picked").

A fixed-depth 3-way self-join is used in place of a recursive CTE: equivalent
result for the 3-hop primary target, clearer SQL, and lets Postgres pick hash
joins instead of nested-loop recursion on 5M edges.
"""
import time
from pathlib import Path

from common.db import connect

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schema" / "003_silver_findings.sql"

TRUNCATE_SQL = """
    TRUNCATE silver.finding, silver.finding_entity, silver.finding_edge
    RESTART IDENTITY CASCADE
"""

# Stage candidate cycles in a temp table. Pre-assign finding_id so the three
# downstream inserts (finding / finding_entity / finding_edge) can share it.
# The chronological join predicates (t2.ts >= t1.ts, t3.ts >= t2.ts, and all
# hops within 14 days of t1) already guarantee exactly one rotation per cycle
# matches — the one whose first hop is chronologically earliest. No LEAST()
# canonicalization by account key: that would fight the chronology and drop
# rings whose time-ordering doesn't start at the alphabetically-smallest node.
STAGE_SQL = """
    CREATE TEMP TABLE cycle_candidates ON COMMIT DROP AS
    WITH e AS (
        SELECT fin_txn_id, from_account_key, to_account_key,
               event_timestamp, amount, currency, payment_format
        FROM silver.transfers_to
        WHERE amount > 1000
    )
    SELECT
        ROW_NUMBER() OVER (ORDER BY t1.event_timestamp, t1.fin_txn_id)::BIGINT AS finding_id,
        t1.fin_txn_id AS txn_hop1, t2.fin_txn_id AS txn_hop2, t3.fin_txn_id AS txn_hop3,
        t1.from_account_key AS acct_a,
        t1.to_account_key   AS acct_b,
        t2.to_account_key   AS acct_c,
        t1.event_timestamp  AS ts_hop1,
        t2.event_timestamp  AS ts_hop2,
        t3.event_timestamp  AS ts_hop3,
        t1.amount AS amt_hop1, t2.amount AS amt_hop2, t3.amount AS amt_hop3,
        t1.currency,
        t1.payment_format AS pf_hop1,
        t2.payment_format AS pf_hop2,
        t3.payment_format AS pf_hop3,
        LEAST   (t1.amount, t2.amount, t3.amount) AS amt_min,
        GREATEST(t1.amount, t2.amount, t3.amount) AS amt_max
    FROM e t1
    JOIN e t2
      ON t2.from_account_key = t1.to_account_key
     AND t2.currency         = t1.currency
     AND t2.event_timestamp >= t1.event_timestamp
     AND t2.event_timestamp <= t1.event_timestamp + INTERVAL '14 days'
    JOIN e t3
      ON t3.from_account_key = t2.to_account_key
     AND t3.to_account_key   = t1.from_account_key
     AND t3.currency         = t1.currency
     AND t3.event_timestamp >= t2.event_timestamp
     AND t3.event_timestamp <= t1.event_timestamp + INTERVAL '14 days'
    WHERE t1.from_account_key <> t2.from_account_key
      AND t2.from_account_key <> t3.from_account_key
      AND t1.from_account_key <> t3.from_account_key
      AND GREATEST(t1.amount, t2.amount, t3.amount)
          <= 1.5 * LEAST(t1.amount, t2.amount, t3.amount)
"""

INSERT_FINDING_SQL = """
    INSERT INTO silver.finding (
        finding_id, assessment_id, finding_type, severity,
        title, description, detected_at, summary_stats,
        control_mapping, sla_trigger_date, sla_duration
    )
    SELECT
        c.finding_id,
        'circular_flow_v1',
        'CIRCULAR_FLOW',
        CASE
            WHEN c.pf_hop1 = c.pf_hop2
             AND c.pf_hop2 = c.pf_hop3
             AND c.amt_max <= 1.2 * c.amt_min
            THEN 'HIGH'
            ELSE 'MEDIUM'
        END AS severity,
        '3-hop circular fund flow: '
            || c.acct_a || ' -> ' || c.acct_b || ' -> '
            || c.acct_c || ' -> ' || c.acct_a AS title,
        'Ring of 3 distinct accounts returning funds to origin over '
            || ROUND(EXTRACT(EPOCH FROM (c.ts_hop3 - c.ts_hop1)) / 3600)::TEXT
            || ' hours. Amount range '
            || c.amt_min::TEXT || '-' || c.amt_max::TEXT || ' ' || c.currency
            || '.' AS description,
        now(),
        jsonb_build_object(
            'hops',           3,
            'currency',       c.currency,
            'amount_min',     c.amt_min,
            'amount_max',     c.amt_max,
            'amount_ratio',   ROUND(c.amt_max / c.amt_min, 4),
            'time_span_hours',ROUND(EXTRACT(EPOCH FROM (c.ts_hop3 - c.ts_hop1)) / 3600),
            'payment_formats',jsonb_build_array(c.pf_hop1, c.pf_hop2, c.pf_hop3),
            'accounts',       jsonb_build_array(c.acct_a, c.acct_b, c.acct_c)
        ),
        cfg.control_mapping,
        c.ts_hop1,
        cfg.sla_duration
    FROM cycle_candidates c
    CROSS JOIN silver.assessment_config cfg
    WHERE cfg.assessment_id = 'circular_flow_v1'
"""

# Related entities: the 3 ring-member Accounts, the Parties that own them
# (via silver.has_account), and the FinancialInstitutions that hold them
# (via silver.is_held_at). UNION dedups when a party owns 2+ of the accounts.
INSERT_FINDING_ENTITY_SQL = """
    INSERT INTO silver.finding_entity (finding_id, entity_type, entity_id, role)
    SELECT finding_id, 'Account', acct, 'ring_member' FROM (
        SELECT finding_id, acct_a AS acct FROM cycle_candidates
        UNION ALL SELECT finding_id, acct_b FROM cycle_candidates
        UNION ALL SELECT finding_id, acct_c FROM cycle_candidates
    ) x
    UNION
    SELECT DISTINCT c.finding_id, 'Party', ha.party_id, 'account_owner'
    FROM cycle_candidates c
    JOIN silver.has_account ha
      ON ha.account_key IN (c.acct_a, c.acct_b, c.acct_c)
    UNION
    SELECT DISTINCT c.finding_id, 'FinancialInstitution', ih.fse_id, 'custodian_bank'
    FROM cycle_candidates c
    JOIN silver.is_held_at ih
      ON ih.account_key IN (c.acct_a, c.acct_b, c.acct_c)
"""

INSERT_FINDING_EDGE_SQL = """
    INSERT INTO silver.finding_edge (
        finding_id, hop_order, edge_type, from_entity, to_entity, fin_txn_id, attrs
    )
    SELECT finding_id, 1, 'transfers_to', acct_a, acct_b, txn_hop1,
           jsonb_build_object(
               'amount', amt_hop1, 'currency', currency,
               'event_timestamp', ts_hop1, 'payment_format', pf_hop1)
    FROM cycle_candidates
    UNION ALL
    SELECT finding_id, 2, 'transfers_to', acct_b, acct_c, txn_hop2,
           jsonb_build_object(
               'amount', amt_hop2, 'currency', currency,
               'event_timestamp', ts_hop2, 'payment_format', pf_hop2)
    FROM cycle_candidates
    UNION ALL
    SELECT finding_id, 3, 'transfers_to', acct_c, acct_a, txn_hop3,
           jsonb_build_object(
               'amount', amt_hop3, 'currency', currency,
               'event_timestamp', ts_hop3, 'payment_format', pf_hop3)
    FROM cycle_candidates
"""


def _timed(cur, name: str, sql: str) -> int:
    t0 = time.perf_counter()
    cur.execute(sql)
    rc = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    print(f"[{name:<24}] {rc:>10,} rows   {time.perf_counter() - t0:>6,.1f}s")
    return rc


def main() -> None:
    ddl = SCHEMA_FILE.read_text()
    with connect() as conn, conn.cursor() as cur:
        t0 = time.perf_counter()
        cur.execute(ddl)
        print(f"[{'apply_ddl':<24}] {'':>10}        {time.perf_counter() - t0:>6,.1f}s")

        _timed(cur, "truncate_findings", TRUNCATE_SQL)
        _timed(cur, "stage_cycles",      STAGE_SQL)
        _timed(cur, "finding",           INSERT_FINDING_SQL)
        _timed(cur, "finding_entity",    INSERT_FINDING_ENTITY_SQL)
        _timed(cur, "finding_edge",      INSERT_FINDING_EDGE_SQL)

        cur.execute("""
            SELECT severity, count(*)
            FROM silver.finding
            GROUP BY severity
            ORDER BY severity
        """)
        rows = cur.fetchall()
        print("\nSeverity breakdown:")
        for sev, n in rows:
            print(f"  {sev:<10} {n:>6,}")

        conn.commit()


if __name__ == "__main__":
    main()
