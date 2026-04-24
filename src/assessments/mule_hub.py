"""Mule-hub detector — fan-in / fan-out assessment.

Run from repo/:
    python -m assessments.mule_hub

Flags accounts that receive from many distinct counterparties AND disperse to
many distinct counterparties in the silver graph — classic mule / collector
topology (§5.1 of docs/kg-model.md).

Thresholds: in_degree >= 10 AND out_degree >= 10 distinct counterparty
accounts. Severity ramps with degree (see MULE_SEVERITY_SQL below).

Graph-native; does NOT read bronze.is_laundering. This is the unsupervised
topological assessment that complements the circular-flow detector.

For each flagged account, finding_entity includes: the hub Account, its
owning Party, its custodian FinancialInstitution, and the top-5 inbound +
top-5 outbound counterparty Accounts (ranked by amount). finding_edge
includes the top-5 inbound + top-5 outbound transfers.
"""
import time
from pathlib import Path

from common.db import connect

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schema" / "003_silver_findings.sql"

TRUNCATE_SQL = """
    DELETE FROM silver.finding WHERE assessment_id = 'mule_hub_v1'
"""

STAGE_SQL = """
    CREATE TEMP TABLE mule_candidates ON COMMIT DROP AS
    WITH out_sum AS (
        SELECT from_account_key AS acct,
               COUNT(DISTINCT to_account_key)  AS out_deg,
               COUNT(*)                        AS out_cnt,
               SUM(amount)                     AS out_total,
               MIN(event_timestamp)            AS out_first,
               MAX(event_timestamp)            AS out_last
        FROM silver.transfers_to
        GROUP BY from_account_key
    ),
    in_sum AS (
        SELECT to_account_key AS acct,
               COUNT(DISTINCT from_account_key) AS in_deg,
               COUNT(*)                         AS in_cnt,
               SUM(amount)                      AS in_total,
               MIN(event_timestamp)             AS in_first,
               MAX(event_timestamp)             AS in_last
        FROM silver.transfers_to
        GROUP BY to_account_key
    ),
    joined AS (
        SELECT i.acct,
               i.in_deg,  o.out_deg,
               i.in_cnt,  o.out_cnt,
               i.in_total, o.out_total,
               LEAST   (i.in_first, o.out_first) AS ts_first,
               GREATEST(i.in_last,  o.out_last)  AS ts_last
        FROM in_sum i JOIN out_sum o USING (acct)
        WHERE i.in_deg >= 10 AND o.out_deg >= 10
    ),
    ccy_rank AS (
        SELECT acct, currency, rn FROM (
            SELECT acct, currency,
                   ROW_NUMBER() OVER (PARTITION BY acct ORDER BY n DESC) AS rn
            FROM (
                SELECT acct, currency, COUNT(*) AS n FROM (
                    SELECT from_account_key AS acct, currency FROM silver.transfers_to
                    UNION ALL
                    SELECT to_account_key,           currency FROM silver.transfers_to
                ) u
                GROUP BY acct, currency
            ) c
        ) r
        WHERE rn = 1
    )
    SELECT
        ROW_NUMBER() OVER (ORDER BY (j.in_deg + j.out_deg) DESC, j.acct) AS local_rank,
        j.acct,
        j.in_deg,  j.out_deg,
        j.in_cnt,  j.out_cnt,
        j.in_total, j.out_total,
        j.ts_first, j.ts_last,
        cr.currency AS dominant_currency,
        LEAST   (j.in_total, j.out_total) AS amt_min,
        GREATEST(j.in_total, j.out_total) AS amt_max
    FROM joined j
    LEFT JOIN ccy_rank cr ON cr.acct = j.acct
"""

# Assign finding_ids that don't collide with existing silver.finding rows.
ASSIGN_IDS_SQL = """
    CREATE TEMP TABLE mule_findings ON COMMIT DROP AS
    WITH base AS (SELECT COALESCE(MAX(finding_id), 0) AS max_id FROM silver.finding)
    SELECT (base.max_id + mc.local_rank)::BIGINT AS finding_id, mc.*
    FROM mule_candidates mc CROSS JOIN base
"""

INSERT_FINDING_SQL = """
    INSERT INTO silver.finding (
        finding_id, assessment_id, finding_type, severity,
        title, description, detected_at, summary_stats,
        control_mapping, sla_trigger_date, sla_duration
    )
    SELECT
        mf.finding_id,
        'mule_hub_v1',
        'MULE_HUB',
        CASE
            WHEN mf.in_deg >= 50 AND mf.out_deg >= 50 THEN 'CRITICAL'
            WHEN mf.in_deg >= 20 AND mf.out_deg >= 20 THEN 'HIGH'
            ELSE 'MEDIUM'
        END AS severity,
        'Mule hub ' || mf.acct
            || ' (' || mf.in_deg || ' in / ' || mf.out_deg || ' out counterparties)'
            AS title,
        'Account ' || mf.acct || ' received from ' || mf.in_deg
            || ' distinct counterparties and dispersed to ' || mf.out_deg
            || ' distinct counterparties over '
            || ROUND(EXTRACT(EPOCH FROM (mf.ts_last - mf.ts_first)) / 3600)::TEXT
            || ' hours.' AS description,
        now(),
        jsonb_build_object(
            'currency',         mf.dominant_currency,
            'in_degree',        mf.in_deg,
            'out_degree',       mf.out_deg,
            'in_txn_count',     mf.in_cnt,
            'out_txn_count',    mf.out_cnt,
            'in_amount_total',  mf.in_total,
            'out_amount_total', mf.out_total,
            'balance_ratio',    CASE WHEN mf.in_total > 0
                                     THEN ROUND(mf.out_total / mf.in_total, 4)
                                     ELSE NULL END,
            'amount_min',       mf.amt_min,
            'amount_max',       mf.amt_max,
            'time_span_hours',  ROUND(EXTRACT(EPOCH FROM (mf.ts_last - mf.ts_first)) / 3600)
        ),
        cfg.control_mapping,
        mf.ts_first,
        cfg.sla_duration
    FROM mule_findings mf
    CROSS JOIN silver.assessment_config cfg
    WHERE cfg.assessment_id = 'mule_hub_v1'
"""

# Entity set per finding:
#  - the hub Account           (role=mule_hub)
#  - owning Party (if known)   (role=account_owner)
#  - custodian FI              (role=custodian_bank)
#  - top-5 inbound counterparty Accounts (by amount)
#  - top-5 outbound counterparty Accounts (by amount)
INSERT_FINDING_ENTITY_SQL = """
    INSERT INTO silver.finding_entity (finding_id, entity_type, entity_id, role)
    SELECT DISTINCT ON (finding_id, entity_type, entity_id)
           finding_id, entity_type, entity_id, role
    FROM (
        SELECT finding_id, 'Account' AS entity_type, acct AS entity_id, 'mule_hub' AS role
        FROM mule_findings
        UNION ALL
        SELECT mf.finding_id, 'Party', ha.party_id, 'account_owner'
        FROM mule_findings mf
        JOIN silver.has_account ha ON ha.account_key = mf.acct
        UNION ALL
        SELECT mf.finding_id, 'FinancialInstitution', a.bank_id, 'custodian_bank'
        FROM mule_findings mf
        JOIN silver.account a ON a.account_key = mf.acct
        UNION ALL
        SELECT finding_id, 'Account', cpty, 'inbound_counterparty'
        FROM (
            SELECT mf.finding_id, t.from_account_key AS cpty,
                   ROW_NUMBER() OVER (PARTITION BY mf.finding_id ORDER BY SUM(t.amount) DESC) AS rn
            FROM mule_findings mf
            JOIN silver.transfers_to t ON t.to_account_key = mf.acct
            GROUP BY mf.finding_id, t.from_account_key
        ) x WHERE rn <= 5
        UNION ALL
        SELECT finding_id, 'Account', cpty, 'outbound_counterparty'
        FROM (
            SELECT mf.finding_id, t.to_account_key AS cpty,
                   ROW_NUMBER() OVER (PARTITION BY mf.finding_id ORDER BY SUM(t.amount) DESC) AS rn
            FROM mule_findings mf
            JOIN silver.transfers_to t ON t.from_account_key = mf.acct
            GROUP BY mf.finding_id, t.to_account_key
        ) y WHERE rn <= 5
    ) all_entities
    ORDER BY finding_id, entity_type, entity_id,
             CASE role
                 WHEN 'mule_hub'              THEN 0
                 WHEN 'account_owner'         THEN 1
                 WHEN 'custodian_bank'        THEN 2
                 WHEN 'inbound_counterparty'  THEN 3
                 WHEN 'outbound_counterparty' THEN 4
                 ELSE 9
             END
"""

# Per finding: top-5 inbound transfers + top-5 outbound transfers by amount.
INSERT_FINDING_EDGE_SQL = """
    INSERT INTO silver.finding_edge (
        finding_id, hop_order, edge_type, from_entity, to_entity, fin_txn_id, attrs
    )
    SELECT finding_id,
           (ROW_NUMBER() OVER (PARTITION BY finding_id ORDER BY side, rnk))::SMALLINT AS hop_order,
           'transfers_to', from_entity, to_entity, fin_txn_id,
           jsonb_build_object(
               'amount', amount, 'currency', currency,
               'event_timestamp', event_timestamp,
               'payment_format', payment_format,
               'direction', side
           )
    FROM (
        SELECT mf.finding_id, 'inbound' AS side,
               t.from_account_key AS from_entity,
               t.to_account_key   AS to_entity,
               t.fin_txn_id, t.amount, t.currency,
               t.event_timestamp, t.payment_format,
               ROW_NUMBER() OVER (PARTITION BY mf.finding_id
                                  ORDER BY t.amount DESC, t.fin_txn_id) AS rnk
        FROM mule_findings mf
        JOIN silver.transfers_to t ON t.to_account_key = mf.acct
        UNION ALL
        SELECT mf.finding_id, 'outbound',
               t.from_account_key, t.to_account_key,
               t.fin_txn_id, t.amount, t.currency,
               t.event_timestamp, t.payment_format,
               ROW_NUMBER() OVER (PARTITION BY mf.finding_id
                                  ORDER BY t.amount DESC, t.fin_txn_id)
        FROM mule_findings mf
        JOIN silver.transfers_to t ON t.from_account_key = mf.acct
    ) ranked
    WHERE rnk <= 5
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

        _timed(cur, "truncate_mule",       TRUNCATE_SQL)
        _timed(cur, "stage_candidates",    STAGE_SQL)
        _timed(cur, "assign_ids",          ASSIGN_IDS_SQL)
        _timed(cur, "finding",             INSERT_FINDING_SQL)
        _timed(cur, "finding_entity",      INSERT_FINDING_ENTITY_SQL)
        _timed(cur, "finding_edge",        INSERT_FINDING_EDGE_SQL)

        cur.execute("""
            SELECT severity, COUNT(*)
            FROM silver.finding WHERE assessment_id = 'mule_hub_v1'
            GROUP BY severity ORDER BY severity
        """)
        rows = cur.fetchall()
        print("\nMule severity breakdown:")
        for sev, n in rows:
            print(f"  {sev:<10} {n:>6,}")

        conn.commit()


if __name__ == "__main__":
    main()
