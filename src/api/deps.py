"""FastAPI dependencies."""
from collections.abc import Iterator

import psycopg
from fastapi import Request


def get_conn(request: Request) -> Iterator[psycopg.Connection]:
    """Check out a connection from the pool for the duration of a request."""
    with request.app.state.pool.connection() as conn:
        yield conn
