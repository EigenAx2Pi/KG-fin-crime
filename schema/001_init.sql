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

CREATE TABLE IF NOT EXISTS bronze.kyc_customers_raw (
    customer_id         TEXT NOT NULL,
    golden_customer_id  TEXT NOT NULL,
    record_source       TEXT,
    full_name           TEXT,
    dob                 DATE,
    country             TEXT,
    address             TEXT,
    phone               TEXT,
    email               TEXT,
    government_id       TEXT,
    risk_tier           TEXT
);

CREATE TABLE IF NOT EXISTS bronze.account_customer_link_raw (
    account_key         TEXT NOT NULL,
    bank_id             TEXT NOT NULL,
    account_id          TEXT NOT NULL,
    customer_id         TEXT NOT NULL,
    golden_customer_id  TEXT NOT NULL,
    relationship        TEXT
);
