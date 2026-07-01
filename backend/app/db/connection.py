import pickle
import re
import sqlite3
from datetime import datetime

import psycopg2
import psycopg2.extras
import psycopg2.pool
from config import ENCODE_FILE, PRODUCTION_DB_PATH
from db_config import DATABASE_URL, DB_TYPE, USE_SUPABASE

DEFAULT_TIME = "1970-01-01 00:00:00"
DEFAULT_MODEL = "edgeface_s_gamma_05"

# --- Connection Pool (Supabase/PostgreSQL) ---
# Lazily initialized on first get_db_connection() call.
_pg_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pg_pool_lock = __import__("threading").Lock()


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
            # Return connection to the pool instead of closing it
            try:
                self.conn.reset()  # clear any uncommitted state
            except Exception:
                pass
            self._pool.putconn(self.conn)
        else:
            self.conn.close()


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
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [dict(r) for r in rows]

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def close(self):
        self.cursor.close()


def get_db_connection():
    if USE_SUPABASE:
        pool = _get_pg_pool()
        pg_conn = pool.getconn()
        return PostgresConnectionWrapper(pg_conn, pool=pool)
    else:
        conn = sqlite3.connect(str(PRODUCTION_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn


def _table_columns(conn, table_name):
    if DB_TYPE == "postgresql":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table_name,),
        ).fetchall()
        return {row["column_name"] for row in rows}
    else:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}


def _add_missing_columns(conn, table_name, columns):
    existing = _table_columns(conn, table_name)
    for column_name, definition in columns.items():
        if column_name not in existing:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )


def _embedding_to_blob(embedding):
    try:
        import numpy as np

        arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
        return arr.tobytes(), int(arr.size)
    except Exception:
        return None, None


def _generate_next_customer_id(conn):
    rows = conn.execute("SELECT customer_id FROM customers").fetchall()
    max_numeric = -1
    for row in rows:
        value = str(row[0] or "")
        if re.fullmatch(r"\d+", value):
            max_numeric = max(max_numeric, int(value))
    return f"{max_numeric + 1:03d}"


def ensure_schema(conn):
    if DB_TYPE == "postgresql":
        # Enable pgvector extension for HNSW-indexed face similarity search
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # Create schema for PostgreSQL / Supabase
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL,
                cameras TEXT,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        _add_missing_columns(
            conn,
            "users",
            {
                "status": "VARCHAR(32) NOT NULL DEFAULT 'active'",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            },
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cameras (
                camera_id VARCHAR(64) PRIMARY KEY,
                display_name VARCHAR(255) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                last_seen_at TIMESTAMP DEFAULT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS camera_device_credentials (
                credential_id VARCHAR(64) PRIMARY KEY,
                camera_id VARCHAR(64) NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
                token_hash VARCHAR(128) UNIQUE NOT NULL,
                created_at TIMESTAMP NOT NULL,
                last_used_at TIMESTAMP DEFAULT NULL,
                expires_at TIMESTAMP DEFAULT NULL,
                revoked_at TIMESTAMP DEFAULT NULL,
                user_agent VARCHAR(512) DEFAULT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_camera_permissions (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                camera_id VARCHAR(64) NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
                permission VARCHAR(32) NOT NULL DEFAULT 'view',
                PRIMARY KEY (user_id, camera_id, permission)
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS camera_connections (
                connection_id VARCHAR(64) PRIMARY KEY,
                camera_id VARCHAR(64) NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
                connected_at TIMESTAMP NOT NULL,
                disconnected_at TIMESTAMP DEFAULT NULL,
                disconnect_reason VARCHAR(255) DEFAULT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                phone VARCHAR(50) DEFAULT NULL,
                email VARCHAR(255) DEFAULT NULL,
                occupation VARCHAR(255) DEFAULT NULL,
                registered_at VARCHAR(255) DEFAULT NULL,
                tenure INTEGER NOT NULL DEFAULT 0,
                loyalty_tier VARCHAR(50) NOT NULL DEFAULT 'Standard',
                total_visits INTEGER NOT NULL DEFAULT 0,
                last_visit VARCHAR(255) NOT NULL DEFAULT '1970-01-01 00:00:00',
                total_spending REAL NOT NULL DEFAULT 0,
                note TEXT DEFAULT NULL,
                customer_type VARCHAR(50) NOT NULL DEFAULT 'registered',
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                created_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customer_embeddings (
                id SERIAL PRIMARY KEY,
                customer_id VARCHAR(255) NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
                face_embedding BYTEA NOT NULL,
                embedding_dim INTEGER NOT NULL DEFAULT 512,
                model_name VARCHAR(100) NOT NULL DEFAULT 'edgeface_s_gamma_05',
                created_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        # Add pgvector column (idempotent — does nothing if it already exists)
        try:
            conn.execute(
                "ALTER TABLE customer_embeddings ADD COLUMN IF NOT EXISTS embedding vector(512)"
            )
        except Exception:
            pass  # Column may already exist

        # Drop old standard vector index if it exists to save space
        try:
            conn.execute("DROP INDEX IF EXISTS idx_customer_embeddings_hnsw")
        except Exception:
            pass

        # Create HNSW index for fast cosine similarity search using halfvec (float16)
        try:
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_customer_embeddings_hnsw_halfvec
                ON customer_embeddings
                USING hnsw ((embedding::halfvec) halfvec_cosine_ops)
                WITH (m = 32, ef_construction = 128)
                """)
        except Exception:
            pass  # Index may already exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT DEFAULT NULL,
                price REAL NOT NULL DEFAULT 0,
                category VARCHAR(255) NOT NULL DEFAULT 'General',
                created_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS table_bookings (
                booking_id VARCHAR(255) PRIMARY KEY,
                customer_id VARCHAR(255) NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
                table_number VARCHAR(50) NOT NULL,
                booking_at VARCHAR(255) NOT NULL,
                party_size INTEGER NOT NULL DEFAULT 1,
                status VARCHAR(50) NOT NULL DEFAULT 'Pending',
                created_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR(255) PRIMARY KEY,
                customer_id VARCHAR(255) NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
                order_date_time VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                total_amount REAL NOT NULL DEFAULT 0,
                status VARCHAR(50) NOT NULL DEFAULT 'Preparing',
                created_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                order_item_id VARCHAR(255) PRIMARY KEY,
                order_id VARCHAR(255) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                product_id VARCHAR(255) NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1,
                subtotal REAL NOT NULL DEFAULT 0,
                created_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recognize_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                opeid UUID NOT NULL,
                camera_id VARCHAR(255) NOT NULL,
                customer_id VARCHAR(255) DEFAULT NULL,
                track_id INTEGER DEFAULT NULL,
                bbox JSONB DEFAULT NULL,
                connection_id VARCHAR(64) DEFAULT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
        _add_missing_columns(
            conn,
            "recognize_logs",
            {"connection_id": "VARCHAR(64) DEFAULT NULL"},
        )
        _add_missing_columns(
            conn,
            "customers",
            {
                "phone": "VARCHAR(50) DEFAULT NULL",
                "email": "VARCHAR(255) DEFAULT NULL",
                "occupation": "VARCHAR(255) DEFAULT NULL",
                "registered_at": "VARCHAR(255) DEFAULT NULL",
                "tenure": "INTEGER NOT NULL DEFAULT 0",
                "loyalty_tier": "VARCHAR(50) NOT NULL DEFAULT 'Standard'",
                "total_visits": "INTEGER NOT NULL DEFAULT 0",
                "last_visit": "VARCHAR(255) NOT NULL DEFAULT '1970-01-01 00:00:00'",
                "total_spending": "REAL NOT NULL DEFAULT 0",
                "note": "TEXT DEFAULT NULL",
                "customer_type": "VARCHAR(50) NOT NULL DEFAULT 'registered'",
                "status": "VARCHAR(50) NOT NULL DEFAULT 'active'",
                "created_at": "VARCHAR(255) DEFAULT NULL",
                "updated_at": "VARCHAR(255) DEFAULT NULL",
            },
        )
        conn.commit()
        try:
            _migrate_embeddings(conn)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Embedding migration skipped: {e}")
        return

    """Create/upgrade local restaurant/customer data schema.

    Main entities:
    - customers: patron identity/contact/profile/visit summary
    - customer_embeddings: face embedding vector per customer
    - products: menu items
    - table_bookings: reservations/check-ins
    - orders: order header
    - order_items: order line items

    Legacy fields are kept as aliases where SQLite already had them, but new code
    should use occupation/registered_at/tenure/loyalty_tier/total_visits/last_visit.
    """

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            cameras TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
    _add_missing_columns(
        conn,
        "users",
        {
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "created_at": "TEXT DEFAULT NULL",
            "updated_at": "TEXT DEFAULT NULL",
        },
    )
    conn.execute(
        "UPDATE users SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "UPDATE users SET updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            camera_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT DEFAULT NULL
        )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS camera_device_credentials (
            credential_id TEXT PRIMARY KEY,
            camera_id TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT DEFAULT NULL,
            expires_at TEXT DEFAULT NULL,
            revoked_at TEXT DEFAULT NULL,
            user_agent TEXT DEFAULT NULL,
            FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_camera_permissions (
            user_id INTEGER NOT NULL,
            camera_id TEXT NOT NULL,
            permission TEXT NOT NULL DEFAULT 'view',
            PRIMARY KEY (user_id, camera_id, permission),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS camera_connections (
            connection_id TEXT PRIMARY KEY,
            camera_id TEXT NOT NULL,
            connected_at TEXT NOT NULL,
            disconnected_at TEXT DEFAULT NULL,
            disconnect_reason TEXT DEFAULT NULL,
            FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT DEFAULT NULL,
            email TEXT DEFAULT NULL,
            occupation TEXT DEFAULT NULL,
            registered_at TEXT DEFAULT NULL,
            tenure INTEGER NOT NULL DEFAULT 0,
            loyalty_tier TEXT NOT NULL DEFAULT 'Standard',
            total_visits INTEGER NOT NULL DEFAULT 0,
            last_visit TEXT NOT NULL DEFAULT '1970-01-01 00:00:00',
            total_spending REAL NOT NULL DEFAULT 0,
            note TEXT DEFAULT NULL,
            customer_type TEXT NOT NULL DEFAULT 'registered',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
    _add_missing_columns(
        conn,
        "customers",
        {
            "phone": "TEXT DEFAULT NULL",
            "email": "TEXT DEFAULT NULL",
            "occupation": "TEXT DEFAULT NULL",
            "registered_at": "TEXT DEFAULT NULL",
            "tenure": "INTEGER NOT NULL DEFAULT 0",
            "loyalty_tier": "TEXT NOT NULL DEFAULT 'Standard'",
            "total_visits": "INTEGER NOT NULL DEFAULT 0",
            "last_visit": "TEXT NOT NULL DEFAULT '1970-01-01 00:00:00'",
            "total_spending": "REAL NOT NULL DEFAULT 0",
            "note": "TEXT DEFAULT NULL",
            "customer_type": "TEXT NOT NULL DEFAULT 'registered'",
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "created_at": "TEXT DEFAULT NULL",
            "updated_at": "TEXT DEFAULT NULL",
        },
    )

    # Create new schema or keep existing if correct
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            face_embedding BLOB NOT NULL,
            embedding_dim INTEGER NOT NULL DEFAULT 512,
            model_name TEXT NOT NULL DEFAULT 'edgeface_s_gamma_05',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
        """)

    # Migration: check if customer_embeddings has 'id' column, if not, migrate it
    columns = _table_columns(conn, "customer_embeddings")
    if "id" not in columns:
        conn.execute(
            "ALTER TABLE customer_embeddings RENAME TO customer_embeddings_old"
        )
        conn.execute("""
            CREATE TABLE customer_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                face_embedding BLOB NOT NULL,
                embedding_dim INTEGER NOT NULL DEFAULT 512,
                model_name TEXT NOT NULL DEFAULT 'edgeface_s_gamma_05',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
            )
            """)
        conn.execute("""
            INSERT INTO customer_embeddings (customer_id, face_embedding, embedding_dim, model_name, created_at, updated_at)
            SELECT customer_id, face_embedding, embedding_dim, model_name, created_at, updated_at FROM customer_embeddings_old
            """)
        conn.execute("DROP TABLE customer_embeddings_old")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT NULL,
            price REAL NOT NULL DEFAULT 0,
            category TEXT NOT NULL DEFAULT 'General',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS table_bookings (
            booking_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            table_number TEXT NOT NULL,
            booking_at TEXT NOT NULL,
            party_size INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            order_date_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            total_amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Preparing',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            order_item_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            subtotal REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS recognize_logs (
            id TEXT PRIMARY KEY,
            opeid TEXT NOT NULL,
            camera_id TEXT NOT NULL,
            customer_id TEXT DEFAULT NULL,
            track_id INTEGER DEFAULT NULL,
            bbox TEXT DEFAULT NULL,
            connection_id TEXT DEFAULT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
    _add_missing_columns(
        conn,
        "recognize_logs",
        {"connection_id": "TEXT DEFAULT NULL"},
    )

    _migrate_legacy_customer_data(conn)
    _migrate_embeddings(conn)
    conn.commit()


def find_active_device_credential(conn, token_hash):
    """Resolve a non-revoked, non-expired device token to its camera."""
    return conn.execute(
        """
        SELECT
            d.credential_id,
            d.camera_id,
            c.display_name,
            c.status
        FROM camera_device_credentials AS d
        JOIN cameras AS c ON c.camera_id = d.camera_id
        WHERE d.token_hash = ?
          AND d.revoked_at IS NULL
          AND (d.expires_at IS NULL OR d.expires_at > CURRENT_TIMESTAMP)
          AND c.status = 'active'
        """,
        (token_hash,),
    ).fetchone()


def create_camera_and_credential(
    conn,
    camera_id,
    display_name,
    credential_id,
    token_hash,
    user_agent=None,
):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO cameras (
            camera_id, display_name, status, created_at, updated_at, last_seen_at
        ) VALUES (?, ?, 'active', ?, ?, ?)
        """,
        (camera_id, display_name, now, now, now),
    )
    conn.execute(
        """
        INSERT INTO camera_device_credentials (
            credential_id, camera_id, token_hash, created_at, last_used_at,
            user_agent
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (credential_id, camera_id, token_hash, now, now, user_agent),
    )


def create_device_credential(
    conn, camera_id, credential_id, token_hash, user_agent=None
):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO camera_device_credentials (
            credential_id, camera_id, token_hash, created_at, last_used_at,
            user_agent
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (credential_id, camera_id, token_hash, now, now, user_agent),
    )
    conn.execute(
        """
        UPDATE cameras
        SET status = 'active', last_seen_at = ?, updated_at = ?
        WHERE camera_id = ?
        """,
        (now, now, camera_id),
    )


def revoke_camera_credentials(conn, camera_id):
    conn.execute(
        """
        UPDATE camera_device_credentials
        SET revoked_at = ?
        WHERE camera_id = ? AND revoked_at IS NULL
        """,
        (datetime.now().isoformat(timespec="seconds"), camera_id),
    )


def retire_replaced_camera(conn, camera_id):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE camera_device_credentials
        SET revoked_at = ?
        WHERE camera_id = ? AND revoked_at IS NULL
        """,
        (now, camera_id),
    )
    conn.execute(
        """
        UPDATE cameras
        SET status = 'replaced', updated_at = ?
        WHERE camera_id = ?
        """,
        (now, camera_id),
    )


def touch_device_credential(conn, credential_id, camera_id):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE camera_device_credentials
        SET last_used_at = ?
        WHERE credential_id = ?
        """,
        (now, credential_id),
    )
    conn.execute(
        """
        UPDATE cameras
        SET last_seen_at = ?, updated_at = ?
        WHERE camera_id = ?
        """,
        (now, now, camera_id),
    )


def list_active_cameras(conn):
    return conn.execute(
        """
        SELECT camera_id, display_name, status, created_at, updated_at, last_seen_at
        FROM cameras
        WHERE status = 'active'
        ORDER BY created_at ASC
        """
    ).fetchall()


def update_camera_display_name(conn, camera_id, display_name):
    cursor = conn.execute(
        """
        UPDATE cameras
        SET display_name = ?, updated_at = ?
        WHERE camera_id = ? AND status = 'active'
        """,
        (display_name, datetime.now().isoformat(timespec="seconds"), camera_id),
    )
    return cursor.rowcount > 0


def list_users_with_permissions(conn):
    active_camera_ids = {
        row["camera_id"] for row in list_active_cameras(conn)
    }
    users = conn.execute(
        """
        SELECT id, username, role, cameras, status, created_at, updated_at
        FROM users
        ORDER BY username ASC
        """
    ).fetchall()
    result = []
    for row in users:
        user = dict(row)
        permission_rows = conn.execute(
            """
            SELECT camera_id
            FROM user_camera_permissions
            WHERE user_id = ? AND permission = 'view'
            ORDER BY camera_id ASC
            """,
            (user["id"],),
        ).fetchall()
        normalized_ids = [
            item["camera_id"]
            for item in permission_rows
            if item["camera_id"] in active_camera_ids
        ]
        legacy_ids = [
            camera_id.strip()
            for camera_id in str(user.pop("cameras") or "").split(",")
            if camera_id.strip() in active_camera_ids
        ]
        user["camera_ids"] = normalized_ids if permission_rows else legacy_ids
        result.append(user)
    return result


def camera_exists(conn, camera_id):
    return conn.execute(
        "SELECT 1 FROM cameras WHERE camera_id = ? AND status = 'active'",
        (camera_id,),
    ).fetchone() is not None


def list_cameras_allowed_for_user(conn, user):
    cameras = [dict(row) for row in list_active_cameras(conn)]
    if user.get("role") == "admin":
        return cameras

    rows = conn.execute(
        """
        SELECT camera_id
        FROM user_camera_permissions
        WHERE user_id = ? AND permission = 'view'
        """,
        (user["id"],),
    ).fetchall()
    normalized_ids = {row["camera_id"] for row in rows}
    legacy_row = conn.execute(
        "SELECT cameras FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    legacy_ids = {
        camera_id.strip()
        for camera_id in str(legacy_row["cameras"] or "").split(",")
        if camera_id.strip()
    } if legacy_row else set()
    allowed_ids = normalized_ids or legacy_ids
    return [camera for camera in cameras if camera["camera_id"] in allowed_ids]


def user_can_view_camera(conn, user, camera_id):
    return any(
        camera["camera_id"] == camera_id
        for camera in list_cameras_allowed_for_user(conn, user)
    )


def replace_user_camera_permissions(conn, user_id, camera_ids):
    conn.execute(
        "DELETE FROM user_camera_permissions WHERE user_id = ? AND permission = 'view'",
        (user_id,),
    )
    for camera_id in camera_ids:
        conn.execute(
            """
            INSERT INTO user_camera_permissions (user_id, camera_id, permission)
            VALUES (?, ?, 'view')
            """,
            (user_id, camera_id),
        )


def record_camera_connection(conn, connection_id, camera_id):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO camera_connections (connection_id, camera_id, connected_at)
        VALUES (?, ?, ?)
        """,
        (connection_id, camera_id, now),
    )


def close_camera_connection(conn, connection_id, reason):
    conn.execute(
        """
        UPDATE camera_connections
        SET disconnected_at = ?, disconnect_reason = ?
        WHERE connection_id = ? AND disconnected_at IS NULL
        """,
        (datetime.now().isoformat(timespec="seconds"), reason, connection_id),
    )


def _migrate_legacy_customer_data(conn):
    cols = _table_columns(conn, "customers")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE customers SET created_at = COALESCE(created_at, ?)", (now,))
    conn.execute("UPDATE customers SET updated_at = COALESCE(updated_at, ?)", (now,))
    conn.execute("UPDATE customers SET name = COALESCE(NULLIF(name, ''), 'Guest')")
    conn.execute(
        "UPDATE customers SET loyalty_tier = COALESCE(NULLIF(loyalty_tier, ''), 'Standard')"
    )
    conn.execute("UPDATE customers SET total_visits = COALESCE(total_visits, 0)")
    conn.execute(
        "UPDATE customers SET last_visit = COALESCE(last_visit, ?)", (DEFAULT_TIME,)
    )
    conn.execute("UPDATE customers SET total_spending = COALESCE(total_spending, 0)")
    conn.execute(
        "UPDATE customers SET customer_type = CASE WHEN customer_id LIKE 'GUEST_%' THEN 'guest' ELSE COALESCE(NULLIF(customer_type, ''), 'registered') END"
    )
    conn.execute(
        "UPDATE customers SET status = CASE WHEN customer_id LIKE 'GUEST_%' THEN 'temporary' ELSE COALESCE(NULLIF(status, ''), 'active') END"
    )

    # Legacy one-table fields from earlier student/customer experiments.
    if "major" in cols:
        conn.execute(
            "UPDATE customers SET occupation = COALESCE(NULLIF(occupation, ''), NULLIF(major, ''))"
        )
    if "starting_year" in cols:
        conn.execute(
            "UPDATE customers SET registered_at = COALESCE(NULLIF(registered_at, ''), CAST(starting_year AS TEXT)) WHERE starting_year IS NOT NULL AND starting_year != 0"
        )
    if "year" in cols:
        conn.execute("UPDATE customers SET tenure = COALESCE(tenure, year)")
    if "standing" in cols:
        conn.execute(
            "UPDATE customers SET loyalty_tier = CASE WHEN loyalty_tier IS NULL OR loyalty_tier = '' OR loyalty_tier = 'Standard' THEN CASE WHEN standing = 'G' THEN 'Standard' ELSE standing END ELSE loyalty_tier END"
        )
    if "total_attendance" in cols:
        conn.execute(
            "UPDATE customers SET total_visits = CASE WHEN total_visits = 0 THEN COALESCE(total_attendance, 0) ELSE total_visits END"
        )
    if "last_attendance_time" in cols:
        conn.execute(
            "UPDATE customers SET last_visit = CASE WHEN last_visit = ? THEN COALESCE(last_attendance_time, ?) ELSE last_visit END",
            (DEFAULT_TIME, DEFAULT_TIME),
        )

    # Migrate previous normalized profile table into Customers.
    profile_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='customer_profiles'"
    ).fetchone()
    if profile_exists:
        profile_cols = _table_columns(conn, "customer_profiles")
        rows = conn.execute("SELECT * FROM customer_profiles").fetchall()
        for row in rows:
            data = dict(row)
            cid = data.get("customer_id")
            if not cid:
                continue
            conn.execute(
                """
                UPDATE customers
                SET
                    name = COALESCE(NULLIF(?, ''), name),
                    phone = COALESCE(NULLIF(?, ''), phone),
                    note = COALESCE(NULLIF(?, ''), note),
                    occupation = COALESCE(NULLIF(?, ''), occupation),
                    registered_at = COALESCE(NULLIF(?, ''), registered_at),
                    tenure = CASE WHEN ? IS NULL THEN tenure ELSE ? END,
                    loyalty_tier = COALESCE(NULLIF(?, ''), loyalty_tier),
                    customer_type = COALESCE(NULLIF(?, ''), customer_type),
                    status = COALESCE(NULLIF(?, ''), status),
                    updated_at = CURRENT_TIMESTAMP
                WHERE customer_id = ?
                """,
                (
                    data.get("name"),
                    data.get("phone"),
                    data.get("note"),
                    data.get("service_category"),
                    (
                        str(data.get("service_start_year"))
                        if data.get("service_start_year")
                        else None
                    ),
                    data.get("customer_tenure_years"),
                    data.get("customer_tenure_years"),
                    data.get("loyalty_tier"),
                    data.get("customer_type"),
                    data.get("status"),
                    cid,
                ),
            )


def _migrate_embeddings(conn):
    # Previous profile-table embedding BLOBs, if present (SQLite legacy only).
    if DB_TYPE != "postgresql":
        profile_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='customer_profiles'"
        ).fetchone()
        if profile_exists and "face_embedding" in _table_columns(
            conn, "customer_profiles"
        ):
            rows = conn.execute(
                "SELECT customer_id, face_embedding, face_embedding_dim, face_embedding_model FROM customer_profiles WHERE face_embedding IS NOT NULL"
            ).fetchall()
            for row in rows:
                # Check if this customer already has this specific embedding vector
                existing = conn.execute(
                    "SELECT COUNT(*) FROM customer_embeddings WHERE customer_id = ? AND face_embedding = ?",
                    (str(row["customer_id"]), row["face_embedding"]),
                ).fetchone()
                count = (
                    existing["count"]
                    if (existing and DB_TYPE == "postgresql")
                    else (existing[0] if existing else 0)
                )
                if count > 0:
                    continue

                conn.execute(
                    """
                    INSERT INTO customer_embeddings (
                        customer_id, face_embedding, embedding_dim, model_name, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        row["customer_id"],
                        row["face_embedding"],
                        row["face_embedding_dim"] or 512,
                        row["face_embedding_model"] or DEFAULT_MODEL,
                    ),
                )

    if not ENCODE_FILE.exists():
        return
    try:
        with open(ENCODE_FILE, "rb") as file:
            payload = pickle.load(file)
    except Exception:
        return
    if not isinstance(payload, (list, tuple)) or len(payload) != 2:
        return

    embeddings, customer_ids = payload
    for embedding, customer_id in zip(embeddings, customer_ids):
        blob, dim = _embedding_to_blob(embedding)
        if not customer_id or blob is None:
            continue

        # Check if this customer already has this specific embedding vector
        existing = conn.execute(
            "SELECT COUNT(*) FROM customer_embeddings WHERE customer_id = ? AND face_embedding = ?",
            (str(customer_id), blob),
        ).fetchone()
        count = (
            existing["count"]
            if (existing and DB_TYPE == "postgresql")
            else (existing[0] if existing else 0)
        )
        if count > 0:
            continue

        if DB_TYPE == "postgresql":
            # Dual-write: BYTEA + pgvector column
            import numpy as np

            arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            vec_str = "[" + ",".join(f"{float(x):.8f}" for x in arr) + "]"
            conn.execute(
                """
                INSERT INTO customer_embeddings (
                    customer_id, face_embedding, embedding_dim, model_name,
                    embedding, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?::vector, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (str(customer_id), blob, dim, DEFAULT_MODEL, vec_str),
            )
        else:
            conn.execute(
                """
                INSERT INTO customer_embeddings (
                    customer_id, face_embedding, embedding_dim, model_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (str(customer_id), blob, dim, DEFAULT_MODEL),
            )


def _row_to_customer(row):
    if not row:
        return None
    data = dict(row)

    # Backward-compatible aliases for current frontend and recognition routes.
    data.setdefault("id", data.get("customer_id"))
    data.setdefault("service_category", data.get("occupation"))
    data.setdefault("service_start_year", data.get("registered_at"))
    data.setdefault("customer_tenure_years", data.get("tenure"))
    data.setdefault("major", data.get("occupation"))
    data.setdefault("starting_year", data.get("registered_at"))
    data.setdefault("year", data.get("tenure"))
    data.setdefault("standing", data.get("loyalty_tier"))
    data.setdefault("total_attendance", data.get("total_visits", 0))
    data.setdefault("last_attendance_time", data.get("last_visit"))
    data.setdefault("visit_count", data.get("total_visits", 0))
    data.setdefault("last_visit", data.get("last_visit"))
    return data


def get_customer_info(conn, customer_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.customer_id,
            c.name,
            c.phone,
            c.email,
            c.occupation,
            c.registered_at,
            c.tenure,
            c.loyalty_tier,
            c.total_visits,
            c.last_visit,
            c.total_spending,
            c.note,
            c.customer_type,
            c.status,
            c.created_at,
            c.updated_at,
            CASE WHEN e.face_embedding IS NULL THEN 0 ELSE 1 END AS has_face_embedding,
            e.embedding_dim AS face_embedding_dim,
            e.model_name AS face_embedding_model,
            e.updated_at AS face_embedding_updated_at
        FROM customers c
        LEFT JOIN customer_embeddings e ON e.customer_id = c.customer_id
        WHERE c.customer_id = ?
        """,
        (customer_id,),
    )
    return _row_to_customer(cursor.fetchone())


def create_or_update_customer_profile(
    conn,
    customer_id=None,
    name=None,
    phone=None,
    note=None,
    source_id=None,
    email=None,
    occupation=None,
    registered_at=None,
    tenure=None,
    loyalty_tier=None,
    service_category=None,
    service_start_year=None,
    customer_tenure_years=None,
):
    clean_id = (customer_id or "").strip()
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Customer name is required")

    occupation = occupation if occupation is not None else service_category
    registered_at = registered_at if registered_at is not None else service_start_year
    tenure = tenure if tenure is not None else customer_tenure_years
    if clean_id.startswith("T") or clean_id.startswith("GUEST_"):
        clean_id = ""

    existing = get_customer_info(conn, clean_id) if clean_id else None
    final_id = clean_id or _generate_next_customer_id(conn)
    created = existing is None

    if created:
        conn.execute(
            """
            INSERT INTO customers (
                customer_id, name, phone, email, occupation, registered_at,
                tenure, loyalty_tier, note, customer_type, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'registered', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                final_id,
                clean_name,
                phone,
                email,
                occupation or "General",
                registered_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                int(tenure or 0),
                loyalty_tier or "Standard",
                note,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE customers
            SET name = ?, phone = ?, note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE customer_id = ?
            """,
            (clean_name, phone, note, final_id),
        )
    conn.commit()
    return final_id, created


def update_attendance(
    conn, customer_id, total_attendance=None, last_attendance_time=None
):
    event_time = last_attendance_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    next_total = total_attendance
    if next_total is None:
        current = get_customer_info(conn, customer_id) or {}
        next_total = int(current.get("total_visits") or 0) + 1
    conn.execute(
        """
        UPDATE customers
        SET total_visits = ?, last_visit = ?, updated_at = CURRENT_TIMESTAMP
        WHERE customer_id = ?
        """,
        (int(next_total or 0), event_time, customer_id),
    )
    conn.commit()


def bulk_insert_recognize_logs(conn, logs):
    """
    Bulk insert recognize logs.
    logs should be a list of dictionaries with keys:
    opeid, camera_id, connection_id, customer_id, track_id, bbox, timestamp
    """
    if not logs:
        return

    import json
    import uuid
    from datetime import datetime

    if DB_TYPE == "postgresql":
        # Ensure we have the underlying psycopg2 connection
        pg_conn = conn.conn
        cursor = pg_conn.cursor()
        query = """
            INSERT INTO recognize_logs (id, opeid, camera_id, connection_id, customer_id, track_id, bbox, timestamp)
            VALUES %s
        """
        values = []
        for log in logs:
            bbox_val = json.dumps(log.get("bbox")) if log.get("bbox") else None
            ts = log.get("timestamp", datetime.now())
            values.append(
                (
                    str(uuid.uuid4()),
                    str(log["opeid"]),
                    str(log["camera_id"]),
                    str(log["connection_id"]) if log.get("connection_id") else None,
                    str(log["customer_id"]) if log.get("customer_id") else None,
                    int(log["track_id"]) if log.get("track_id") is not None else None,
                    bbox_val,
                    ts,
                )
            )
        try:
            psycopg2.extras.execute_values(cursor, query, values)
            pg_conn.commit()
        except Exception as e:
            pg_conn.rollback()
            print(f"Bulk insert recognize logs failed: {e}")
        finally:
            cursor.close()
    else:
        # SQLite
        query = """
            INSERT INTO recognize_logs (id, opeid, camera_id, connection_id, customer_id, track_id, bbox, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = []
        for log in logs:
            bbox_val = json.dumps(log.get("bbox")) if log.get("bbox") else None
            ts = log.get("timestamp", datetime.now().isoformat())
            if isinstance(ts, datetime):
                ts = ts.isoformat()
            values.append(
                (
                    str(uuid.uuid4()),
                    str(log["opeid"]),
                    str(log["camera_id"]),
                    str(log["connection_id"]) if log.get("connection_id") else None,
                    str(log["customer_id"]) if log.get("customer_id") else None,
                    int(log["track_id"]) if log.get("track_id") is not None else None,
                    bbox_val,
                    ts,
                )
            )
        try:
            cursor = conn.cursor()
            cursor.executemany(query, values)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Bulk insert recognize logs failed: {e}")


def upsert_customer(
    conn,
    customer_id,
    name,
    occupation="General",
    registered_at=None,
    total_visits=0,
    loyalty_tier="Standard",
    tenure=0,
    last_visit=DEFAULT_TIME,
    phone=None,
    email=None,
    note=None,
    total_spending=0,
    customer_type="registered",
    status="active",
    **legacy_kwargs,
):
    # Accept old seed/function names while migrating.
    occupation = legacy_kwargs.get("service_category", occupation)
    registered_at = legacy_kwargs.get("service_start_year", registered_at)
    tenure = legacy_kwargs.get("customer_tenure_years", tenure)
    total_visits = legacy_kwargs.get("total_attendance", total_visits)
    last_visit = legacy_kwargs.get("last_attendance_time", last_visit)

    if isinstance(registered_at, int):
        registered_at = str(registered_at)

    conn.execute(
        """
        INSERT INTO customers (
            customer_id, name, phone, email, occupation, registered_at, tenure,
            loyalty_tier, total_visits, last_visit, total_spending, note,
            customer_type, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(customer_id) DO UPDATE SET
            name = excluded.name,
            phone = excluded.phone,
            email = excluded.email,
            occupation = excluded.occupation,
            registered_at = excluded.registered_at,
            tenure = excluded.tenure,
            loyalty_tier = excluded.loyalty_tier,
            total_visits = excluded.total_visits,
            last_visit = excluded.last_visit,
            total_spending = excluded.total_spending,
            note = excluded.note,
            customer_type = excluded.customer_type,
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            customer_id,
            name,
            phone,
            email,
            occupation or "General",
            str(registered_at or DEFAULT_TIME),
            int(tenure or 0),
            loyalty_tier or "Standard",
            int(total_visits or 0),
            last_visit or DEFAULT_TIME,
            float(total_spending or 0),
            note,
            customer_type,
            status,
        ),
    )
    conn.commit()


def insert_guest_record(conn, guest_id):
    upsert_customer(
        conn,
        guest_id,
        "Guest",
        occupation="Walk-in customer",
        registered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_visits=0,
        loyalty_tier="Standard",
        tenure=0,
        last_visit=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        customer_type="guest",
        status="temporary",
    )
