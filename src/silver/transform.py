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
        SELECT DISTINCT b, 'Bank ' || b
        FROM (
            SELECT bank_id AS b FROM bronze.account_customer_link_raw
            UNION SELECT from_bank FROM bronze.transactions_raw
            UNION SELECT to_bank   FROM bronze.transactions_raw
        ) u
    """),
    ("account", """
        INSERT INTO silver.account (account_key, bank_id, account_id)
        SELECT DISTINCT account_key, bank_id, account_id
        FROM (
            SELECT account_key, bank_id, account_id
              FROM bronze.account_customer_link_raw
            UNION
            SELECT from_bank || ':' || from_account, from_bank, from_account
              FROM bronze.transactions_raw
            UNION
            SELECT to_bank || ':' || to_account, to_bank, to_account
              FROM bronze.transactions_raw
        ) u
    """),
    ("party", """
        INSERT INTO silver.party (
            party_id, source_customer_id, record_source, name,
            date_of_birth, country_of_residence, address_text,
            phone, email, government_id, risk_tier
        )
        SELECT DISTINCT ON (golden_customer_id)
               golden_customer_id, customer_id, record_source, full_name,
               dob, country, address, phone, email, government_id, risk_tier
        FROM bronze.kyc_customers_raw
        ORDER BY golden_customer_id
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
        INSERT INTO silver.has_account (party_id, account_key, relationship, source)
        SELECT DISTINCT ON (golden_customer_id, account_key)
               golden_customer_id, account_key, relationship,
               'HI-Small_Account_Customer_Link.csv'
        FROM bronze.account_customer_link_raw
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
