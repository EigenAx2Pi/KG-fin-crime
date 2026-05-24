"""Bronze loader — streams HI-Small CSVs into bronze.* via COPY FROM STDIN.

Run from repo/ (picks up .env from CWD):
    python -m bronze.load                 # all targets
    python -m bronze.load --only trans    # just one of: trans | accounts

Idempotent — each target is TRUNCATEd before load.
"""
import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from common.db import connect

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "../data")).resolve()

TARGETS: dict[str, tuple[str, str]] = {
    "trans": ("bronze.transactions_raw", "HI-Small_Trans.csv"),
    "accounts": ("bronze.accounts_raw", "HI-Small_accounts.csv"),
}


def load_one(name: str) -> None:
    table, filename = TARGETS[name]
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(path)
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"[{name}] {path.name} ({size_mb:,.1f} MB) -> {table}")

    t0 = time.perf_counter()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {table}")
        with cur.copy(f"COPY {table} FROM STDIN WITH (FORMAT CSV, HEADER)") as copy:
            with open(path, "rb") as f:
                while chunk := f.read(1 << 20):
                    copy.write(chunk)
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        (n,) = cur.fetchone()
    dt = time.perf_counter() - t0
    print(f"[{name}] {n:,} rows in {dt:,.1f}s ({n / max(dt, 1e-3):,.0f} rows/s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(TARGETS))
    args = ap.parse_args()
    for name in ([args.only] if args.only else list(TARGETS)):
        load_one(name)


if __name__ == "__main__":
    main()
