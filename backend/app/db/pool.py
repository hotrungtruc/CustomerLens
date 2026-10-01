"""
Database connection pool & low-level wrappers.

Provides:
  - PostgresConnectionWrapper / PostgresCursorWrapper  — uniform dict-row interface
  - get_db_connection()  — returns a connection (SQLite or pooled PostgreSQL)
"""

import sqlite3
import threading

import psycopg2
import psycopg2.extras
import psycopg2.pool
from config import PRODUCTION_DB_PATH
from db_config import DATABASE_URL, DB_TYPE, USE_SUPABASE

try:
    from pgvector.psycopg2 import register_vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

# ---------------------------------------------------------------------------
# PostgreSQL connection pool  (lazy, singleton)
# ---------------------------------------------------------------------------

_pg_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pg_pool_lock = threading.Lock()


def _get_pg_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the global connection pool, creating it on first call."""
    global _pg_pool
    if _pg_pool is None or _pg_pool.closed:
        with _pg_pool_lock:
            if _pg_pool is None or _pg_pool.closed:
                _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=10,
                    dsn=DATABASE_URL,
                )
    return _pg_pool


# ---------------------------------------------------------------------------
# Wrappers — give PostgreSQL the same dict-row interface as sqlite3.Row
# ---------------------------------------------------------------------------

class PostgresCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, parameters=None):
        # Convert SQLite ? placeholders to PostgreSQL %s
        sql = sql.replace("?", "%s")
        if parameters:
            self.cursor.execute(sql, parameters)
        else:
            self.cursor.execute(sql)
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self.cursor.fetchall()]

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def close(self):
        self.cursor.close()


class PostgresConnectionWrapper:
    def __init__(self, conn, pool=None):
        self.conn = conn
        self._pool = pool  # if set, close() returns conn to pool

    def cursor(self):
        return PostgresCursorWrapper(
            self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        )

    def execute(self, sql, parameters=None):
        cursor = self.cursor()
        cursor.execute(sql, parameters)
        return cursor

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        if self._pool is not None:
            try:
                self.conn.reset()  # clear any uncommitted state
            except Exception:
                pass
            self._pool.putconn(self.conn)
        else:
            self.conn.close()


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def get_db_connection():
    """Return a database connection (PostgreSQL wrapper or raw SQLite connection)."""
    if USE_SUPABASE:
        pool = _get_pg_pool()
        pg_conn = pool.getconn()
        if HAS_PGVECTOR:
            try:
                register_vector(pg_conn)
            except Exception:
                pass
        return PostgresConnectionWrapper(pg_conn, pool=pool)
    else:
        conn = sqlite3.connect(str(PRODUCTION_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
