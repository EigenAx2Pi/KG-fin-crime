-- Silver findings layer — assessment configuration + findings + related entities/edges.
-- Mirrors sds-product-em's assessment/finding shape: persisted AssessmentConfig,
-- finding with control_mapping + SLA envelope, and related-entity / related-edge tables
-- for drill-down in the UI. See notes/reference-alignment.md for rationale.

------------------------------------------------------------------
-- Assessment configuration (mirrors sds-product-em AssessmentConfig)
------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.assessment_config (
    assessment_id       TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    description         TEXT,
    severity_default    TEXT NOT NULL,
    scope_query         TEXT NOT NULL,
    success_condition   TEXT NOT NULL,
    finding_config      JSONB NOT NULL,
    control_mapping     JSONB,
    sla_duration        INTERVAL,
    created_at          TIMESTAMP NOT NULL DEFAULT now()
);

------------------------------------------------------------------
-- Findings
------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.finding (
    finding_id          BIGINT PRIMARY KEY,
    assessment_id       TEXT NOT NULL REFERENCES silver.assessment_config(assessment_id),
    finding_type        TEXT NOT NULL,
    severity            TEXT NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT,
    detected_at         TIMESTAMP NOT NULL DEFAULT now(),
    summary_stats       JSONB NOT NULL,
    control_mapping     JSONB,
    sla_trigger_date    TIMESTAMP,
    sla_action_date     TIMESTAMP,
    sla_duration        INTERVAL
);

CREATE TABLE IF NOT EXISTS silver.finding_entity (
    finding_id     BIGINT NOT NULL REFERENCES silver.finding(finding_id) ON DELETE CASCADE,
    entity_type    TEXT   NOT NULL,
    entity_id      TEXT   NOT NULL,
    role           TEXT,
    PRIMARY KEY (finding_id, entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS silver.finding_edge (
    finding_id     BIGINT   NOT NULL REFERENCES silver.finding(finding_id) ON DELETE CASCADE,
    hop_order      SMALLINT NOT NULL,
    edge_type      TEXT     NOT NULL,
    from_entity    TEXT     NOT NULL,
    to_entity      TEXT     NOT NULL,
    fin_txn_id     BIGINT   REFERENCES silver.financial_transaction(fin_txn_id),
    attrs          JSONB,
    PRIMARY KEY (finding_id, hop_order)
);

CREATE INDEX IF NOT EXISTS ix_finding_severity      ON silver.finding (severity);
CREATE INDEX IF NOT EXISTS ix_finding_type          ON silver.finding (finding_type);
CREATE INDEX IF NOT EXISTS ix_finding_entity_entity ON silver.finding_entity (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_finding_edge_fintxn   ON silver.finding_edge (fin_txn_id);

------------------------------------------------------------------
-- Seed: circular_flow_v1 assessment (idempotent — re-upserted on every run)
------------------------------------------------------------------

INSERT INTO silver.assessment_config (
    assessment_id, title, description, severity_default,
    scope_query, success_condition, finding_config,
    control_mapping, sla_duration
) VALUES (
    'circular_flow_v1',
    'Circular fund flow (3-hop laundering ring)',
    'Detects closed cycles across 3 distinct accounts where money returns to origin within a short window and a comparable amount.',
    'HIGH',
    'SELECT * FROM silver.transfers_to WHERE amount > 1000',
    'A -> B -> C -> A with 3 distinct accounts AND max(ts) - min(ts) <= INTERVAL ''14 days'' AND max(amount) / min(amount) <= 1.5 AND single currency.',
    '{"hops": 3, "max_time_span_days": 14, "max_amount_ratio": 1.5, "min_amount": 1000, "same_currency": true}'::JSONB,
    '{"BSA": "31 CFR 1020.320 (Suspicious Activity Reports)", "FATF": "R.20 (Reporting of suspicious transactions)", "EU_AMLD": "Directive 2015/849 Art. 33"}'::JSONB,
    INTERVAL '72 hours'
)
ON CONFLICT (assessment_id) DO UPDATE SET
    title             = EXCLUDED.title,
    description       = EXCLUDED.description,
    severity_default  = EXCLUDED.severity_default,
    scope_query       = EXCLUDED.scope_query,
    success_condition = EXCLUDED.success_condition,
    finding_config    = EXCLUDED.finding_config,
    control_mapping   = EXCLUDED.control_mapping,
    sla_duration      = EXCLUDED.sla_duration;

------------------------------------------------------------------
-- Seed: mule_hub_v1 — graph-native, unsupervised (fan-in / fan-out)
------------------------------------------------------------------

INSERT INTO silver.assessment_config (
    assessment_id, title, description, severity_default,
    scope_query, success_condition, finding_config,
    control_mapping, sla_duration
) VALUES (
    'mule_hub_v1',
    'Mule-hub fan-in / fan-out',
    'Detects accounts that receive from many distinct counterparties AND disperse to many distinct counterparties — classic mule / collector-account topology. Graph-native; no labels.',
    'HIGH',
    'SELECT from_account_key, to_account_key, amount, currency, event_timestamp FROM silver.transfers_to',
    'Account.in_degree (distinct counterparties) >= 10 AND Account.out_degree (distinct counterparties) >= 10.',
    '{"min_in_degree": 10, "min_out_degree": 10, "top_counterparties_per_side": 5, "top_transfers_per_side": 5}'::JSONB,
    '{"BSA": "31 CFR 1020.320 (Suspicious Activity Reports)", "FATF": "R.10 (Customer due diligence) / R.20 (Reporting)", "EU_AMLD": "Directive 2015/849 Art. 18 (Enhanced CDD)"}'::JSONB,
    INTERVAL '72 hours'
)
ON CONFLICT (assessment_id) DO UPDATE SET
    title             = EXCLUDED.title,
    description       = EXCLUDED.description,
    severity_default  = EXCLUDED.severity_default,
    scope_query       = EXCLUDED.scope_query,
    success_condition = EXCLUDED.success_condition,
    finding_config    = EXCLUDED.finding_config,
    control_mapping   = EXCLUDED.control_mapping,
    sla_duration      = EXCLUDED.sla_duration;

------------------------------------------------------------------
-- Seed: laundering_exposure_v1 — supervised signal (reads ground-truth label)
------------------------------------------------------------------

INSERT INTO silver.assessment_config (
    assessment_id, title, description, severity_default,
    scope_query, success_condition, finding_config,
    control_mapping, sla_duration
) VALUES (
    'laundering_exposure_v1',
    'Laundering-labelled exposure (supervised)',
    'Ranks accounts by exposure to transactions flagged IsLaundering=1 in the AMLSim ground-truth label. Supervised complement to the graph-native assessments — used when a training label IS available.',
    'HIGH',
    'SELECT * FROM bronze.transactions_raw WHERE is_laundering = 1',
    'Count of labeled transfers touching an Account (as source or destination) >= 20.',
    '{"min_labeled_edges": 20, "top_transfers": 10, "top_counterparties_per_side": 3}'::JSONB,
    '{"BSA": "31 CFR 1020.320 (Suspicious Activity Reports)", "FATF": "R.10 (Customer due diligence)", "EU_AMLD": "Directive 2015/849 Art. 33"}'::JSONB,
    INTERVAL '48 hours'
)
ON CONFLICT (assessment_id) DO UPDATE SET
    title             = EXCLUDED.title,
    description       = EXCLUDED.description,
    severity_default  = EXCLUDED.severity_default,
    scope_query       = EXCLUDED.scope_query,
    success_condition = EXCLUDED.success_condition,
    finding_config    = EXCLUDED.finding_config,
    control_mapping   = EXCLUDED.control_mapping,
    sla_duration      = EXCLUDED.sla_duration;
