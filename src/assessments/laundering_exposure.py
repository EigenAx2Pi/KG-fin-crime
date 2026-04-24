"""Laundering-exposure detector — supervised-signal assessment.

Run from repo/:
    python -m assessments.laundering_exposure

This is the **supervised** complement to the graph-native assessments
(circular_flow, mule_hub). It openly uses the AMLSim `IsLaundering=1`
ground-truth label on `bronze.transactions_raw` and ranks accounts by
exposure to labeled transactions (§5.3 of docs/kg-model.md).

Framing for Pillar-1:
  * circular_flow / mule_hub — "what the graph reveals without any label"
  * laundering_exposure      — "what the label-supervised baseline surfaces"
  Together they demonstrate the platform supports both regimes with the
  same silver.assessment_config / silver.finding shape.

Threshold: an account is flagged if it touches >= 20 labeled transactions
(as source or destination). Severity ramps with count.
"""
import time
from pathlib import Path

from common.db import connect

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schema" / "003_silver_findings.sql"

TRUNCATE_SQL = """
    DELETE FROM silver.finding WHERE assessment_id = 'laundering_exposure_v1'
"""

# Bronze rows that are labeled laundering; join back to silver.transfers_to
# so we can reference them by fin_txn_id in silver.finding_edge.
STAGE_LABELED_SQL = """
    CREATE TEMP TABLE labeled_edges ON COMMIT DROP AS
    SELECT t.fin_txn_id, t.from_account_key, t.to_account_key,
           t.event_timestamp, t.amount, t.currency, t.payment_format
    FROM silver.transfers_to t
    JOIN bronze.transactions_raw b
      ON b.event_timestamp                      = t.event_timestamp
     AND (b.from_bank || ':' || b.from_account) = t.from_account_key
     AND (b.to_bank   || ':' || b.to_account)   = t.to_account_key
     AND b.amount_paid                          = t.amount
    WHERE b.is_laundering = 1
"""

STAGE_CANDIDATES_SQL = """
    CREATE TEMP TABLE lx_candidates ON COMMIT DROP AS
    WITH touches AS (
        SELECT from_account_key AS acct, fin_txn_id, amount, currency, event_timestamp FROM labeled_edges
        UNION ALL
        SELECT to_account_key,            fin_txn_id, amount, currency, event_timestamp FROM labeled_edges
    ),
    per_acct AS (
        SELECT acct,
               COUNT(*)                         AS labeled_edges,
               COUNT(DISTINCT fin_txn_id)       AS distinct_labeled_txns,
               SUM(amount)                      AS labeled_amount_total,
               MIN(amount)                      AS amt_min,
               MAX(amount)                      AS amt_max,
               MIN(event_timestamp)             AS ts_first,
               MAX(event_timestamp)             AS ts_last
        FROM touches GROUP BY acct
        HAVING COUNT(*) >= 20
    ),
    dom_ccy AS (
        SELECT acct, currency FROM (
            SELECT acct, currency,
                   ROW_NUMBER() OVER (PARTITION BY acct ORDER BY n DESC) AS rn
            FROM (
                SELECT acct, currency, COUNT(*) AS n FROM touches GROUP BY acct, currency
            ) c
        ) r WHERE rn = 1
    )
    SELECT
        ROW_NUMBER() OVER (ORDER BY pa.labeled_edges DESC, pa.acct) AS local_rank,
        pa.acct,
        pa.labeled_edges, pa.distinct_labeled_txns,
        pa.labeled_amount_total,
        pa.amt_min, pa.amt_max,
        pa.ts_first, pa.ts_last,
        dc.currency AS dominant_currency
    FROM per_acct pa
    LEFT JOIN dom_ccy dc ON dc.acct = pa.acct
"""

ASSIGN_IDS_SQL = """
    CREATE TEMP TABLE lx_findings ON COMMIT DROP AS
    WITH base AS (SELECT COALESCE(MAX(finding_id), 0) AS max_id FROM silver.finding)
    SELECT (base.max_id + lx.local_rank)::BIGINT AS finding_id, lx.*
    FROM lx_candidates lx CROSS JOIN base
"""

INSERT_FINDING_SQL = """
    INSERT INTO silver.finding (
        finding_id, assessment_id, finding_type, severity,
        title, description, detected_at, summary_stats,
        control_mapping, sla_trigger_date, sla_duration
    )
    SELECT
        lx.finding_id,
        'laundering_exposure_v1',
        'LAUNDERING_EXPOSURE',
        CASE
            WHEN lx.labeled_edges >= 50 THEN 'CRITICAL'
            WHEN lx.labeled_edges >= 30 THEN 'HIGH'
            ELSE 'MEDIUM'
        END AS severity,
        'Labeled exposure: ' || lx.acct
            || ' (' || lx.labeled_edges || ' labeled transfers)' AS title,
        'Account ' || lx.acct || ' participates in ' || lx.labeled_edges
            || ' transactions flagged IsLaundering=1 by the AMLSim ground-truth '
            || 'label. Label-driven, supervised — contrast with graph-native assessments.'
            AS description,
        now(),
        jsonb_build_object(
            'currency',              lx.dominant_currency,
            'labeled_edges',         lx.labeled_edges,
            'distinct_labeled_txns', lx.distinct_labeled_txns,
            'labeled_amount_total',  lx.labeled_amount_total,
            'amount_min',            lx.amt_min,
            'amount_max',            lx.amt_max,
            'time_span_hours',       ROUND(EXTRACT(EPOCH FROM (lx.ts_last - lx.ts_first)) / 3600)
        ),
        cfg.control_mapping,
        lx.ts_first,
        cfg.sla_duration
    FROM lx_findings lx
    CROSS JOIN silver.assessment_config cfg
    WHERE cfg.assessment_id = 'laundering_exposure_v1'
"""

# Entity set: exposed Account + owning Party + custodian FI + top-3 inbound
# and top-3 outbound counterparty Accounts (by labeled amount).
INSERT_FINDING_ENTITY_SQL = """
    INSERT INTO silver.finding_entity (finding_id, entity_type, entity_id, role)
    SELECT DISTINCT ON (finding_id, entity_type, entity_id)
           finding_id, entity_type, entity_id, role
    FROM (
        SELECT finding_id, 'Account' AS entity_type, acct AS entity_id,
               'exposed_account' AS role
        FROM lx_findings
        UNION ALL
        SELECT lx.finding_id, 'Party', ha.party_id, 'account_owner'
        FROM lx_findings lx
        JOIN silver.has_account ha ON ha.account_key = lx.acct
        UNION ALL
        SELECT lx.finding_id, 'FinancialInstitution', a.bank_id, 'custodian_bank'
        FROM lx_findings lx
        JOIN silver.account a ON a.account_key = lx.acct
        UNION ALL
        SELECT finding_id, 'Account', cpty, 'inbound_counterparty'
        FROM (
            SELECT lx.finding_id, le.from_account_key AS cpty,
                   ROW_NUMBER() OVER (PARTITION BY lx.finding_id ORDER BY SUM(le.amount) DESC) AS rn
            FROM lx_findings lx
            JOIN labeled_edges le ON le.to_account_key = lx.acct
            GROUP BY lx.finding_id, le.from_account_key
        ) x WHERE rn <= 3
        UNION ALL
        SELECT finding_id, 'Account', cpty, 'outbound_counterparty'
        FROM (
            SELECT lx.finding_id, le.to_account_key AS cpty,
                   ROW_NUMBER() OVER (PARTITION BY lx.finding_id ORDER BY SUM(le.amount) DESC) AS rn
            FROM lx_findings lx
            JOIN labeled_edges le ON le.from_account_key = lx.acct
            GROUP BY lx.finding_id, le.to_account_key
        ) y WHERE rn <= 3
    ) all_entities
    ORDER BY finding_id, entity_type, entity_id,
             CASE role
                 WHEN 'exposed_account'       THEN 0
                 WHEN 'account_owner'         THEN 1
                 WHEN 'custodian_bank'        THEN 2
                 WHEN 'inbound_counterparty'  THEN 3
                 WHEN 'outbound_counterparty' THEN 4
                 ELSE 9
             END
"""

# Per finding: top-10 labeled transfers touching the account, by amount.
INSERT_FINDING_EDGE_SQL = """
    INSERT INTO silver.finding_edge (
        finding_id, hop_order, edge_type, from_entity, to_entity, fin_txn_id, attrs
    )
    SELECT finding_id,
           (ROW_NUMBER() OVER (PARTITION BY finding_id ORDER BY side, rnk))::SMALLINT,
           'transfers_to', from_entity, to_entity, fin_txn_id,
           jsonb_build_object(
               'amount', amount, 'currency', currency,
               'event_timestamp', event_timestamp,
               'payment_format', payment_format,
               'direction', side,
               'is_laundering', true
           )
    FROM (
        SELECT lx.finding_id, 'inbound' AS side,
               le.from_account_key AS from_entity,
               le.to_account_key   AS to_entity,
               le.fin_txn_id, le.amount, le.currency,
               le.event_timestamp, le.payment_format,
               ROW_NUMBER() OVER (PARTITION BY lx.finding_id
                                  ORDER BY le.amount DESC, le.fin_txn_id) AS rnk
        FROM lx_findings lx
        JOIN labeled_edges le ON le.to_account_key = lx.acct
        UNION ALL
        SELECT lx.finding_id, 'outbound',
               le.from_account_key, le.to_account_key,
               le.fin_txn_id, le.amount, le.currency,
               le.event_timestamp, le.payment_format,
               ROW_NUMBER() OVER (PARTITION BY lx.finding_id
                                  ORDER BY le.amount DESC, le.fin_txn_id)
        FROM lx_findings lx
        JOIN labeled_edges le ON le.from_account_key = lx.acct
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

        _timed(cur, "truncate_lx",       TRUNCATE_SQL)
        _timed(cur, "stage_labeled",     STAGE_LABELED_SQL)
        _timed(cur, "stage_candidates",  STAGE_CANDIDATES_SQL)
        _timed(cur, "assign_ids",        ASSIGN_IDS_SQL)
        _timed(cur, "finding",           INSERT_FINDING_SQL)
        _timed(cur, "finding_entity",    INSERT_FINDING_ENTITY_SQL)
        _timed(cur, "finding_edge",      INSERT_FINDING_EDGE_SQL)

        cur.execute("""
            SELECT severity, COUNT(*)
            FROM silver.finding WHERE assessment_id = 'laundering_exposure_v1'
            GROUP BY severity ORDER BY severity
        """)
        rows = cur.fetchall()
        print("\nLaundering-exposure severity breakdown:")
        for sev, n in rows:
            print(f"  {sev:<10} {n:>6,}")

        conn.commit()


if __name__ == "__main__":
    main()
