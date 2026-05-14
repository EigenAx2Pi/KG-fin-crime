"""Gold publisher — materialize silver.finding* into gold.* for the API/UI.

Run from repo/:
    python -m gold.publish

Silver keeps raw JSONB; gold flattens everything the FastAPI layer needs and
denormalizes entity names / countries / risk tiers / bank names so each row
is one thing the UI can render directly. The API should never touch silver.*.

Idempotent — TRUNCATE ... RESTART IDENTITY CASCADE up front, re-inserts
everything from silver on each run.
"""
import time
from pathlib import Path

from common.db import connect

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schema" / "004_gold.sql"

STATEMENTS: list[tuple[str, str]] = [
    ("truncate", """
        TRUNCATE gold.finding, gold.finding_entity, gold.finding_edge
        RESTART IDENTITY CASCADE
    """),
    ("finding", """
        INSERT INTO gold.finding (
            finding_id, assessment_id, finding_type, severity, title, description,
            detected_at,
            hop_count, currency, amount_min, amount_max, amount_ratio, time_span_hours,
            control_bsa, control_fatf, control_eu_amld,
            sla_trigger_date, sla_due_date, sla_duration,
            party_count, bank_count, country_count, countries, banks
        )
        SELECT
            f.finding_id, f.assessment_id, f.finding_type, f.severity,
            f.title, f.description, f.detected_at,
            (f.summary_stats->>'hops')::SMALLINT,
            f.summary_stats->>'currency',
            (f.summary_stats->>'amount_min')::NUMERIC(20,4),
            (f.summary_stats->>'amount_max')::NUMERIC(20,4),
            (f.summary_stats->>'amount_ratio')::NUMERIC(10,4),
            (f.summary_stats->>'time_span_hours')::INTEGER,
            f.control_mapping->>'BSA',
            f.control_mapping->>'FATF',
            f.control_mapping->>'EU_AMLD',
            f.sla_trigger_date,
            f.sla_trigger_date + f.sla_duration,
            f.sla_duration,
            agg.party_count, agg.bank_count, agg.country_count,
            agg.countries, agg.banks
        FROM silver.finding f
        LEFT JOIN LATERAL (
            SELECT
                count(*) FILTER (WHERE fe.entity_type = 'Party')::INT                AS party_count,
                count(*) FILTER (WHERE fe.entity_type = 'FinancialInstitution')::INT AS bank_count,
                count(DISTINCT p.country_of_residence)::INT                          AS country_count,
                array_agg(DISTINCT p.country_of_residence)
                    FILTER (WHERE p.country_of_residence IS NOT NULL)                AS countries,
                array_agg(DISTINCT fi.name)
                    FILTER (WHERE fi.name IS NOT NULL)                               AS banks
            FROM silver.finding_entity fe
            LEFT JOIN silver.party p
                   ON fe.entity_type = 'Party' AND p.party_id = fe.entity_id
            LEFT JOIN silver.financial_institution fi
                   ON fe.entity_type = 'FinancialInstitution' AND fi.fse_id = fe.entity_id
            WHERE fe.finding_id = f.finding_id
        ) agg ON TRUE
    """),
    ("finding_entity", """
        INSERT INTO gold.finding_entity (
            finding_id, entity_type, entity_id, role,
            display_name, country, risk_tier, bank_id, bank_name, owner_party_id
        )
        SELECT
            fe.finding_id, fe.entity_type, fe.entity_id, fe.role,
            CASE fe.entity_type
                WHEN 'Party'                THEN p.name
                WHEN 'FinancialInstitution' THEN fi1.name
                WHEN 'Account'              THEN fe.entity_id
            END AS display_name,
            p.country_of_residence,
            p.risk_tier,
            a.bank_id,
            CASE fe.entity_type
                WHEN 'Account'              THEN fi2.name
                WHEN 'FinancialInstitution' THEN fi1.name
            END AS bank_name,
            owner.party_id AS owner_party_id
        FROM silver.finding_entity fe
        LEFT JOIN silver.party p
               ON fe.entity_type = 'Party'                AND p.party_id    = fe.entity_id
        LEFT JOIN silver.financial_institution fi1
               ON fe.entity_type = 'FinancialInstitution' AND fi1.fse_id    = fe.entity_id
        LEFT JOIN silver.account a
               ON fe.entity_type = 'Account'              AND a.account_key = fe.entity_id
        LEFT JOIN silver.financial_institution fi2
               ON fe.entity_type = 'Account'              AND fi2.fse_id    = a.bank_id
        LEFT JOIN LATERAL (
            SELECT ha.party_id
            FROM silver.has_account ha
            WHERE fe.entity_type = 'Account'
              AND ha.account_key = fe.entity_id
              AND ha.party_id IN (
                  SELECT entity_id FROM silver.finding_entity
                  WHERE finding_id = fe.finding_id AND entity_type = 'Party'
              )
            ORDER BY CASE ha.relationship WHEN 'PRIMARY_OWNER' THEN 0 ELSE 1 END,
                     ha.party_id
            LIMIT 1
        ) owner ON TRUE
    """),
    ("finding_edge", """
        INSERT INTO gold.finding_edge (
            finding_id, hop_order, edge_type,
            from_account_key, to_account_key,
            from_bank_id, to_bank_id,
            fin_txn_id, amount, currency, event_timestamp, payment_format
        )
        SELECT
            fe.finding_id, fe.hop_order, fe.edge_type,
            fe.from_entity, fe.to_entity,
            af.bank_id, at2.bank_id,
            fe.fin_txn_id,
            (fe.attrs->>'amount')::NUMERIC(20,4),
            fe.attrs->>'currency',
            (fe.attrs->>'event_timestamp')::TIMESTAMP,
            fe.attrs->>'payment_format'
        FROM silver.finding_edge fe
        LEFT JOIN silver.account af  ON af.account_key  = fe.from_entity
        LEFT JOIN silver.account at2 ON at2.account_key = fe.to_entity
    """),
]


def main() -> None:
    ddl = SCHEMA_FILE.read_text()
    with connect() as conn, conn.cursor() as cur:
        t0 = time.perf_counter()
        cur.execute(ddl)
        print(f"[{'apply_ddl':<24}]                    {time.perf_counter() - t0:>6,.1f}s")
        for name, sql in STATEMENTS:
            t0 = time.perf_counter()
            cur.execute(sql)
            rc = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
            print(f"[{name:<24}] {rc:>10,} rows   {time.perf_counter() - t0:>6,.1f}s")
        conn.commit()


if __name__ == "__main__":
    main()
