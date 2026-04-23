-- Silver layer — FIBO-aligned KG per docs/kg-model.md.
-- 4 node types (Party, FinancialInstitution, Account, FinancialTransaction)
-- + 5 edge types (hasAccount, isHeldAt, hasOriginatingAccount, hasBeneficiaryAccount, transfersTo).
-- is_laundering from bronze is intentionally NOT propagated here (see notes/decisions.md).

------------------------------------------------------------------
-- Nodes
------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.party (
    party_id               TEXT PRIMARY KEY,
    source_customer_id     TEXT NOT NULL,
    record_source          TEXT,
    name                   TEXT,
    date_of_birth          DATE,
    country_of_residence   TEXT,
    address_text           TEXT,
    phone                  TEXT,
    email                  TEXT,
    government_id          TEXT,
    risk_tier              TEXT
);

CREATE TABLE IF NOT EXISTS silver.financial_institution (
    fse_id   TEXT PRIMARY KEY,
    name     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.account (
    account_key   TEXT PRIMARY KEY,
    bank_id       TEXT NOT NULL REFERENCES silver.financial_institution(fse_id),
    account_id    TEXT NOT NULL,
    currency      TEXT
);

CREATE TABLE IF NOT EXISTS silver.financial_transaction (
    fin_txn_id          BIGINT PRIMARY KEY,
    event_timestamp     TIMESTAMP     NOT NULL,
    amount_paid         NUMERIC(20,4) NOT NULL,
    payment_currency    TEXT          NOT NULL,
    amount_received     NUMERIC(20,4) NOT NULL,
    receiving_currency  TEXT          NOT NULL,
    payment_format      TEXT          NOT NULL,
    source              TEXT
);

------------------------------------------------------------------
-- Edges
------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.has_account (
    party_id       TEXT NOT NULL REFERENCES silver.party(party_id),
    account_key    TEXT NOT NULL REFERENCES silver.account(account_key),
    relationship   TEXT,
    source         TEXT,
    PRIMARY KEY (party_id, account_key)
);

CREATE TABLE IF NOT EXISTS silver.is_held_at (
    account_key   TEXT NOT NULL REFERENCES silver.account(account_key),
    fse_id        TEXT NOT NULL REFERENCES silver.financial_institution(fse_id),
    PRIMARY KEY (account_key, fse_id)
);

CREATE TABLE IF NOT EXISTS silver.has_originating_account (
    fin_txn_id    BIGINT NOT NULL REFERENCES silver.financial_transaction(fin_txn_id),
    account_key   TEXT   NOT NULL REFERENCES silver.account(account_key),
    PRIMARY KEY (fin_txn_id)
);

CREATE TABLE IF NOT EXISTS silver.has_beneficiary_account (
    fin_txn_id    BIGINT NOT NULL REFERENCES silver.financial_transaction(fin_txn_id),
    account_key   TEXT   NOT NULL REFERENCES silver.account(account_key),
    PRIMARY KEY (fin_txn_id)
);

-- Derived convenience edge: one row per transaction, Account -> Account directly.
-- This is what the circular-flow detector traverses.
CREATE TABLE IF NOT EXISTS silver.transfers_to (
    fin_txn_id          BIGINT PRIMARY KEY REFERENCES silver.financial_transaction(fin_txn_id),
    from_account_key    TEXT          NOT NULL REFERENCES silver.account(account_key),
    to_account_key      TEXT          NOT NULL REFERENCES silver.account(account_key),
    event_timestamp     TIMESTAMP     NOT NULL,
    amount              NUMERIC(20,4) NOT NULL,
    currency            TEXT          NOT NULL,
    payment_format      TEXT          NOT NULL
);

------------------------------------------------------------------
-- Indexes for graph traversal
------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS ix_transfers_to_from ON silver.transfers_to (from_account_key);
CREATE INDEX IF NOT EXISTS ix_transfers_to_to   ON silver.transfers_to (to_account_key);
CREATE INDEX IF NOT EXISTS ix_transfers_to_ts   ON silver.transfers_to (event_timestamp);
CREATE INDEX IF NOT EXISTS ix_has_account_acct  ON silver.has_account (account_key);
CREATE INDEX IF NOT EXISTS ix_orig_account_key  ON silver.has_originating_account (account_key);
CREATE INDEX IF NOT EXISTS ix_bene_account_key  ON silver.has_beneficiary_account (account_key);
CREATE INDEX IF NOT EXISTS ix_fintxn_ts         ON silver.financial_transaction (event_timestamp);
