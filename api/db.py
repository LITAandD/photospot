"""Each application owns its pool; each request owns one transaction.

The connection is checked out lazily on first use, so provider calls that run
before any query never hold a pooled connection. `release()` commits and returns
it early (e.g. before a slow external call); the next query checks out a new one.
The dependency must be used with scope="function" (see DB) so the commit runs
before the response is sent and a failed commit becomes an error response.
"""
from fastapi import Depends, Request
from psycopg_pool import ConnectionPool


def init_pool(dsn: str) -> ConnectionPool:
    # Importing the application to generate OpenAPI must not connect to a database.
    return ConnectionPool(dsn, min_size=0, max_size=10, timeout=5, open=False)


class LazyConnection:
    def __init__(self, pool: ConnectionPool):
        self._pool, self._conn = pool, None

    def _get(self):
        if self._conn is None:
            if self._pool.closed:
                self._pool.open()
            self._conn = self._pool.getconn()
        return self._conn

    def __getattr__(self, name):
        return getattr(self._get(), name)

    @property
    def acquired(self) -> bool:
        return self._conn is not None

    def release(self, failed: bool = False) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            if not failed:
                conn.commit()           # A failed commit propagates as an error response.
            elif not conn.closed:
                try:
                    conn.rollback()
                except Exception:
                    pass                # Keep the original error; the pool discards broken connections.
        finally:
            self._pool.putconn(conn)


def release(conn) -> None:
    """Commit and return the pooled connection before slow non-DB work."""
    if isinstance(conn, LazyConnection):
        conn.release()


def get_conn(request: Request):
    conn = LazyConnection(request.app.state.pool)
    try:
        yield conn
    except BaseException:
        conn.release(failed=True)
        raise
    conn.release()


# Function scope: commit/rollback finishes before the response is sent.
DB = Depends(get_conn, scope="function")
