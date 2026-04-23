"""KG-fin-crime FastAPI app.

Serves gold.* tables to the UI. Matches the reference platform's API layer
pattern (sds-product-em, sds-platform-apps/knowledge-graph-api are both
FastAPI). Run from repo/:

    uvicorn api.main:app --reload

Queries gold.* only — silver and bronze are not reachable through this API.
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool

from api.routes import findings

load_dotenv()

CONN_STR = " ".join(
    [
        f"host={os.environ['PGHOST']}",
        f"port={os.environ['PGPORT']}",
        f"dbname={os.environ['PGDATABASE']}",
        f"user={os.environ['PGUSER']}",
        f"password={os.environ['PGPASSWORD']}",
    ]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = ConnectionPool(conninfo=CONN_STR, min_size=1, max_size=5, open=True)
    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


app = FastAPI(
    title="KG-fin-crime API",
    description="Findings and graph drill-down over gold.*",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(findings.router)


@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, bool]:
    return {"ok": True}
