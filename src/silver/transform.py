"""Silver transform — populates silver.* from bronze.* via pure SQL.

Run from repo/:
    python -m silver.transform

Idempotent — TRUNCATE ... RESTART IDENTITY CASCADE up front.

Order is FK-safe: nodes before edges, parents before children. A session-local
TEMP table (txns_numbered) gives deterministic fin_txn_id across the FinTxn
node + its three edge tables.

is_laundering is NOT propagated from bronze (see notes/decisions.md).
"""
import time

from common.db import connect

STATEMENTS: list[tuple[str, str]] = [
    ("truncate", """
        TRUNCATE silver.financial_institution, silver.account, silver.party,
                 silver.financial_transaction,
                 silver.has_account, silver.is_held_at,
                 silver.has_originating_account, silver.has_beneficiary_account,
                 silver.transfers_to
        RESTART IDENTITY CASCADE
    """),
    ("financial_institution", """
        INSERT INTO silver.financial_institution (fse_id, name)
        SELECT b, COALESCE(MAX(bank_name), 'Bank ' || b)
        FROM (
            SELECT bank_id AS b, bank_name FROM bronze.accounts_raw
            UNION ALL SELECT from_bank, NULL FROM bronze.transactions_raw
            UNION ALL SELECT to_bank,   NULL FROM bronze.transactions_raw
        ) u
        GROUP BY b
    """),
    ("account", """
        INSERT INTO silver.account (account_key, bank_id, account_id)
        SELECT DISTINCT account_key, bank_id, account_id
        FROM (
            SELECT bank_id || ':' || account_id AS account_key, bank_id, account_id
              FROM bronze.accounts_raw
            UNION
            SELECT from_bank || ':' || from_account, from_bank, from_account
              FROM bronze.transactions_raw
            UNION
            SELECT to_bank || ':' || to_account, to_bank, to_account
              FROM bronze.transactions_raw
        ) u
    """),
    ("party", """
        -- Parties from two sources:
        --   1) bronze.accounts_raw — real entity ledger (entity_id, entity_name)
        --   2) Transaction account_keys that have no accounts_raw match —
        --      synthesized 1:1 with record_source='SYNTHESIZED' so UI/README
        --      can disclose the synthesis. Under the post-July-2025 AMLSim
        --      layout the two ledgers are disjoint; without (2) every finding
        --      would render with party_count=0.
        INSERT INTO silver.party (
            party_id, source_customer_id, record_source, name,
            date_of_birth, country_of_residence, address_text,
            phone, email, government_id, risk_tier
        )
        SELECT DISTINCT ON (party_id)
               party_id, source_customer_id, record_source, name,
               NULL::DATE, NULL, NULL, NULL, NULL, NULL, NULL
        FROM (
            SELECT entity_id AS party_id, entity_id AS source_customer_id,
                   'HI-Small_accounts.csv' AS record_source, entity_name AS name
            FROM bronze.accounts_raw
            UNION
            SELECT from_bank || ':' || from_account, from_bank || ':' || from_account,
                   'SYNTHESIZED (1:1 party-per-account)', from_bank || ':' || from_account
            FROM bronze.transactions_raw
            UNION
            SELECT to_bank || ':' || to_account, to_bank || ':' || to_account,
                   'SYNTHESIZED (1:1 party-per-account)', to_bank || ':' || to_account
            FROM bronze.transactions_raw
        ) u
        ORDER BY party_id, record_source  -- 'HI-Small_accounts.csv' < 'SYNTHESIZED' alphabetically; real wins on collision
    """),
    ("stage_txns", """
        CREATE TEMP TABLE txns_numbered ON COMMIT DROP AS
        SELECT
            ROW_NUMBER() OVER (
                ORDER BY event_timestamp,
                         from_bank, from_account,
                         to_bank,   to_account,
                         amount_paid
            )::BIGINT AS fin_txn_id,
            event_timestamp,
            from_bank, from_account,
            to_bank,   to_account,
            amount_received, receiving_currency,
            amount_paid,     payment_currency,
            payment_format
        FROM bronze.transactions_raw
    """),
    ("financial_transaction", """
        INSERT INTO silver.financial_transaction (
            fin_txn_id, event_timestamp,
            amount_paid, payment_currency,
            amount_received, receiving_currency,
            payment_format, source
        )
        SELECT fin_txn_id, event_timestamp,
               amount_paid, payment_currency,
               amount_received, receiving_currency,
               payment_format, 'HI-Small_Trans.csv'
        FROM txns_numbered
    """),
    ("has_originating_account", """
        INSERT INTO silver.has_originating_account (fin_txn_id, account_key)
        SELECT fin_txn_id, from_bank || ':' || from_account FROM txns_numbered
    """),
    ("has_beneficiary_account", """
        INSERT INTO silver.has_beneficiary_account (fin_txn_id, account_key)
        SELECT fin_txn_id, to_bank || ':' || to_account FROM txns_numbered
    """),
    ("transfers_to", """
        INSERT INTO silver.transfers_to (
            fin_txn_id, from_account_key, to_account_key,
            event_timestamp, amount, currency, payment_format
        )
        SELECT fin_txn_id,
               from_bank || ':' || from_account,
               to_bank   || ':' || to_account,
               event_timestamp, amount_paid, payment_currency, payment_format
        FROM txns_numbered
    """),
    ("has_account", """
        -- Account ownership from accounts_raw + synthesized 1:1 ownership for
        -- transaction-only accounts. The synthesized party_id equals the
        -- account_key, so the FK to silver.party is satisfied by the synthesized
        -- party rows above.
        INSERT INTO silver.has_account (party_id, account_key, relationship, source)
        SELECT DISTINCT ON (party_id, account_key)
               party_id, account_key, NULL, source
        FROM (
            SELECT entity_id AS party_id, bank_id || ':' || account_id AS account_key,
                   'HI-Small_accounts.csv' AS source
            FROM bronze.accounts_raw
            UNION
            SELECT from_bank || ':' || from_account, from_bank || ':' || from_account,
                   'SYNTHESIZED (1:1 party-per-account)'
            FROM bronze.transactions_raw
            UNION
            SELECT to_bank || ':' || to_account, to_bank || ':' || to_account,
                   'SYNTHESIZED (1:1 party-per-account)'
            FROM bronze.transactions_raw
        ) u
        ORDER BY party_id, account_key, source
    """),
    ("is_held_at", """
        INSERT INTO silver.is_held_at (account_key, fse_id)
        SELECT account_key, bank_id FROM silver.account
    """),
]


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        for name, sql in STATEMENTS:
            t0 = time.perf_counter()
            cur.execute(sql)
            rc = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
            print(f"[{name:<24}] {rc:>10,} rows   {time.perf_counter() - t0:>6,.1f}s")
        conn.commit()


if __name__ == "__main__":
    main()
