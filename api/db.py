"""Each application owns its pool; each request owns one transaction."""
from fastapi import Request
from psycopg_pool import ConnectionPool

def init_pool(dsn: str) -> ConnectionPool:
    # Importing the application to generate OpenAPI must not connect to a database.
    return ConnectionPool(dsn, min_size=0, max_size=10, timeout=5, open=False)


def get_conn(request: Request):
    pool = request.app.state.pool
    if pool.closed:
        pool.open()
    with pool.connection() as conn:
        yield conn
