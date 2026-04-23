-- Gold layer — display-ready, API-facing projection of silver.finding*.
-- JSONB is unpacked into typed columns; entity rows are denormalized with
-- party names / countries / risk tiers / bank names so the UI gets one row
-- per thing it renders. The FastAPI service queries these tables directly
-- and should never need to touch silver.* or bronze.*.

------------------------------------------------------------------
-- Findings (one row per detected ring)
------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gold.finding (
    finding_id          BIGINT PRIMARY KEY,
    assessment_id       TEXT      NOT NULL,
    finding_type        TEXT      NOT NULL,
    severity            TEXT      NOT NULL,
    title               TEXT      NOT NULL,
    description         TEXT,
    detected_at         TIMESTAMP NOT NULL,

    -- summary_stats unpacked
    hop_count           SMALLINT,
    currency            TEXT,
    amount_min          NUMERIC(20,4),
    amount_max          NUMERIC(20,4),
    amount_ratio        NUMERIC(10,4),
    time_span_hours     INTEGER,

    -- control_mapping unpacked (BSA / FATF / EU_AMLD)
    control_bsa         TEXT,
    control_fatf        TEXT,
    control_eu_amld     TEXT,

    -- SLA envelope (EM shape; not enforced in demo)
    sla_trigger_date    TIMESTAMP,
    sla_due_date        TIMESTAMP,
    sla_duration        INTERVAL,

    -- list-view aggregates (computed once at publish; keeps /findings cheap)
    party_count         INTEGER,
    bank_count          INTEGER,
    country_count       INTEGER,
    countries           TEXT[],
    banks               TEXT[]
);

CREATE INDEX IF NOT EXISTS ix_gold_finding_severity ON gold.finding (severity);
CREATE INDEX IF NOT EXISTS ix_gold_finding_detected ON gold.finding (detected_at);

------------------------------------------------------------------
-- Finding entities (denormalized for per-finding graph view)
------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gold.finding_entity (
    finding_id          BIGINT NOT NULL REFERENCES gold.finding(finding_id) ON DELETE CASCADE,
    entity_type         TEXT   NOT NULL,   -- Account / Party / FinancialInstitution
    entity_id           TEXT   NOT NULL,
    role                TEXT,              -- ring_member / account_owner / custodian_bank
    display_name        TEXT,              -- party name / bank name / account key
    country             TEXT,              -- populated for Party
    risk_tier           TEXT,              -- populated for Party
    bank_id             TEXT,              -- populated for Account
    bank_name           TEXT,              -- populated for Account + FinancialInstitution
    PRIMARY KEY (finding_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS ix_gold_finding_entity_fid ON gold.finding_entity (finding_id);

------------------------------------------------------------------
-- Finding edges (flattened attrs + denormalized bank IDs)
------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gold.finding_edge (
    finding_id          BIGINT   NOT NULL REFERENCES gold.finding(finding_id) ON DELETE CASCADE,
    hop_order           SMALLINT NOT NULL,
    edge_type           TEXT     NOT NULL,
    from_account_key    TEXT     NOT NULL,
    to_account_key      TEXT     NOT NULL,
    from_bank_id        TEXT,
    to_bank_id          TEXT,
    fin_txn_id          BIGINT,
    amount              NUMERIC(20,4),
    currency            TEXT,
    event_timestamp     TIMESTAMP,
    payment_format      TEXT,
    PRIMARY KEY (finding_id, hop_order)
);

CREATE INDEX IF NOT EXISTS ix_gold_finding_edge_fid ON gold.finding_edge (finding_id);
