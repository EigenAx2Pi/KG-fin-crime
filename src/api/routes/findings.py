"""Finding routes — list, detail, per-finding graph drill-down."""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row

from api.deps import get_conn
from api.models import FindingDetail, FindingGraph, FindingSummary

router = APIRouter(prefix="/findings", tags=["findings"])

# severity buckets are ordered from most to least critical so the default
# list view surfaces HIGH/CRITICAL first without a client-side sort.
SEVERITY_ORDER = """
    CASE severity
        WHEN 'CRITICAL' THEN 0
        WHEN 'HIGH'     THEN 1
        WHEN 'MEDIUM'   THEN 2
        WHEN 'LOW'      THEN 3
        ELSE 4
    END
"""


@router.get("", response_model=list[FindingSummary])
def list_findings(
    severity: str | None = Query(None, description="Filter by severity"),
    limit: int = Query(50, ge=1, le=500),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    where = "WHERE severity = %s" if severity else ""
    params: list = [severity] if severity else []
    params.append(limit)
    sql = f"""
        SELECT finding_id, severity, finding_type, title, detected_at,
               currency, amount_min, amount_max, time_span_hours,
               party_count, bank_count, country_count, countries, banks
        FROM gold.finding
        {where}
        ORDER BY {SEVERITY_ORDER}, detected_at DESC
        LIMIT %s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


@router.get("/{finding_id}", response_model=FindingDetail)
def get_finding(
    finding_id: int,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT finding_id, assessment_id, finding_type, severity, title,
                   description, detected_at, hop_count, currency,
                   amount_min, amount_max, amount_ratio, time_span_hours,
                   control_bsa, control_fatf, control_eu_amld,
                   sla_trigger_date, sla_due_date, sla_duration,
                   party_count, bank_count, country_count, countries, banks
            FROM gold.finding
            WHERE finding_id = %s
            """,
            (finding_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"finding {finding_id} not found")
    return row


@router.get("/{finding_id}/graph", response_model=FindingGraph)
def get_finding_graph(
    finding_id: int,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT 1 FROM gold.finding WHERE finding_id = %s", (finding_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"finding {finding_id} not found")

        cur.execute(
            """
            SELECT entity_type, entity_id, role, display_name,
                   country, risk_tier, bank_id, bank_name, owner_party_id
            FROM gold.finding_entity
            WHERE finding_id = %s
            ORDER BY entity_type, entity_id
            """,
            (finding_id,),
        )
        entities = cur.fetchall()

        cur.execute(
            """
            SELECT hop_order, edge_type, from_account_key, to_account_key,
                   from_bank_id, to_bank_id, fin_txn_id, amount, currency,
                   event_timestamp, payment_format
            FROM gold.finding_edge
            WHERE finding_id = %s
            ORDER BY hop_order
            """,
            (finding_id,),
        )
        edges = cur.fetchall()

    return {"finding_id": finding_id, "entities": entities, "edges": edges}
