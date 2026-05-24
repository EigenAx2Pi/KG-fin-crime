"""Pydantic response models for the KG-fin-crime API.

Shapes mirror gold.* column layouts one-to-one — no transforms in the route
handlers, cursor dict rows map directly into these models.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel


class FindingSummary(BaseModel):
    finding_id: int
    severity: str
    finding_type: str
    title: str
    detected_at: datetime
    currency: str | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    time_span_hours: int | None = None
    party_count: int | None = None
    bank_count: int | None = None
    country_count: int | None = None
    countries: list[str] | None = None
    banks: list[str] | None = None


class FindingDetail(FindingSummary):
    assessment_id: str
    description: str | None = None
    hop_count: int | None = None
    amount_ratio: Decimal | None = None
    control_bsa: str | None = None
    control_fatf: str | None = None
    control_eu_amld: str | None = None
    sla_trigger_date: datetime | None = None
    sla_due_date: datetime | None = None
    sla_duration: timedelta | None = None


class GraphEntity(BaseModel):
    entity_type: str
    entity_id: str
    role: str | None = None
    display_name: str | None = None
    country: str | None = None
    risk_tier: str | None = None
    bank_id: str | None = None
    bank_name: str | None = None
    owner_party_id: str | None = None


class GraphEdge(BaseModel):
    hop_order: int
    edge_type: str
    from_account_key: str
    to_account_key: str
    from_bank_id: str | None = None
    to_bank_id: str | None = None
    fin_txn_id: int | None = None
    amount: Decimal | None = None
    currency: str | None = None
    event_timestamp: datetime | None = None
    payment_format: str | None = None


class FindingGraph(BaseModel):
    finding_id: int
    entities: list[GraphEntity]
    edges: list[GraphEdge]
