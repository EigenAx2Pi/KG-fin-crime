-- Medallion schemas. All three live in one DB.
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- Bronze: faithful mirror of the source CSVs. Minimal typing, no joins, no derived columns.
-- is_laundering is retained as ground truth; it MUST NOT be read by the detector or
-- propagated into silver/gold (see notes/decisions.md 2026-04-23 "Demo ring picked").
CREATE TABLE IF NOT EXISTS bronze.transactions_raw (
    event_timestamp     TIMESTAMP    NOT NULL,
    from_bank           TEXT         NOT NULL,
    from_account        TEXT         NOT NULL,
    to_bank             TEXT         NOT NULL,
    to_account          TEXT         NOT NULL,
    amount_received     NUMERIC(20,4) NOT NULL,
    receiving_currency  TEXT         NOT NULL,
    amount_paid         NUMERIC(20,4) NOT NULL,
    payment_currency    TEXT         NOT NULL,
    payment_format      TEXT         NOT NULL,
    is_laundering       SMALLINT     NOT NULL
);

-- Schema for the post-July-2025 AMLSim layout. The original release shipped
-- separate KYC + Account-Customer-Link files; IBM consolidated them into a
-- single accounts.csv with no KYC detail. silver.party retains its richer KYC
-- columns but they are NULL-populated from this loader.
CREATE TABLE IF NOT EXISTS bronze.accounts_raw (
    bank_name      TEXT NOT NULL,
    bank_id        TEXT NOT NULL,
    account_id     TEXT NOT NULL,
    entity_id      TEXT NOT NULL,
    entity_name    TEXT NOT NULL
);
