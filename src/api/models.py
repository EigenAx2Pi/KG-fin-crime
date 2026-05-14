"""Pydantic response models for the KG-fin-crime API.

Shapes mirror gold.* column layouts one-to-one — no transforms in the route
handlers, cursor dict rows map directly into these models.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class FindingSummary(BaseModel):
    finding_id: int
    severity: str
    finding_type: str
    title: str
    detected_at: datetime
    currency: Optional[str] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    time_span_hours: Optional[int] = None
    party_count: Optional[int] = None
    bank_count: Optional[int] = None
    country_count: Optional[int] = None
    countries: Optional[list[str]] = None
    banks: Optional[list[str]] = None


class FindingDetail(FindingSummary):
    assessment_id: str
    description: Optional[str] = None
    hop_count: Optional[int] = None
    amount_ratio: Optional[Decimal] = None
    control_bsa: Optional[str] = None
    control_fatf: Optional[str] = None
    control_eu_amld: Optional[str] = None
    sla_trigger_date: Optional[datetime] = None
    sla_due_date: Optional[datetime] = None
    sla_duration: Optional[timedelta] = None


class GraphEntity(BaseModel):
    entity_type: str
    entity_id: str
    role: Optional[str] = None
    display_name: Optional[str] = None
    country: Optional[str] = None
    risk_tier: Optional[str] = None
    bank_id: Optional[str] = None
    bank_name: Optional[str] = None
    owner_party_id: Optional[str] = None


class GraphEdge(BaseModel):
    hop_order: int
    edge_type: str
    from_account_key: str
    to_account_key: str
    from_bank_id: Optional[str] = None
    to_bank_id: Optional[str] = None
    fin_txn_id: Optional[int] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    event_timestamp: Optional[datetime] = None
    payment_format: Optional[str] = None


class FindingGraph(BaseModel):
    finding_id: int
    entities: list[GraphEntity]
    edges: list[GraphEdge]
