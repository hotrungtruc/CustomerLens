"""
Database schema management: table creation, migrations, and audit columns.

Provides:
  - ensure_schema(conn)   — idempotent create + migrate on startup
  - Internal helpers: _table_columns, _add_missing_columns, _add_all_audit_columns,
    _migrate_legacy_customer_data, _migrate_embeddings, _embedding_to_blob
"""

import pickle
import re
from datetime import datetime

from config import ENCODE_FILE
from db_config import DB_TYPE

DEFAULT_TIME = "1970-01-01 00:00:00"
DEFAULT_MODEL = "edgeface_s_gamma_05"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

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


def _add_all_audit_columns(conn):
    audit_cols_pg = {
        "opeid": "VARCHAR(255)",
        "reg_id": "VARCHAR(255)",
        "reg_dt": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "upd_id": "VARCHAR(255)",
        "upd_dt": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "del_id": "VARCHAR(255)",
        "del_dt": "TIMESTAMP",
        "del_yn": "VARCHAR(1) DEFAULT 'N'",
    }
    audit_cols_sl = {
        "opeid": "TEXT",
        "reg_id": "TEXT",
        "reg_dt": "TEXT DEFAULT CURRENT_TIMESTAMP",
        "upd_id": "TEXT",
        "upd_dt": "TEXT DEFAULT CURRENT_TIMESTAMP",
        "del_id": "TEXT",
        "del_dt": "TEXT",
        "del_yn": "TEXT DEFAULT 'N'",
    }
    cols = audit_cols_pg if DB_TYPE == "postgresql" else audit_cols_sl
    tables = [
        "users", "cameras", "camera_device_credentials",
        "user_camera_permissions", "camera_connections",
        "customers", "customer_embeddings", "recognize_logs",
    ]
    for t in tables:
        try:
            _add_missing_columns(conn, t, cols)
        except Exception as e:
            print(f"Warning: could not add audit columns to {t}: {e}")


def _embedding_to_blob(embedding):
    try:
        import numpy as np
        arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
        return arr.tobytes(), int(arr.size)
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Legacy data migrations
# ---------------------------------------------------------------------------

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
        "UPDATE customers SET customer_type = CASE WHEN customer_id LIKE 'GUEST_%' THEN 'guest'"
        " ELSE COALESCE(NULLIF(customer_type, ''), 'registered') END"
    )
    conn.execute(
        "UPDATE customers SET status = CASE WHEN customer_id LIKE 'GUEST_%' THEN 'temporary'"
        " ELSE COALESCE(NULLIF(status, ''), 'active') END"
    )

    # Legacy one-table fields from earlier student/customer experiments
    if "major" in cols:
        conn.execute(
            "UPDATE customers SET occupation = COALESCE(NULLIF(occupation, ''), NULLIF(major, ''))"
        )
    if "starting_year" in cols:
        conn.execute(
            "UPDATE customers SET registered_at = COALESCE(NULLIF(registered_at, ''), "
            "CAST(starting_year AS TEXT)) WHERE starting_year IS NOT NULL AND starting_year != 0"
        )
    if "year" in cols:
        conn.execute("UPDATE customers SET tenure = COALESCE(tenure, year)")
    if "standing" in cols:
        conn.execute(
            "UPDATE customers SET loyalty_tier = CASE WHEN loyalty_tier IS NULL OR loyalty_tier = ''"
            " OR loyalty_tier = 'Standard' THEN CASE WHEN standing = 'G' THEN 'Standard'"
            " ELSE standing END ELSE loyalty_tier END"
        )
    if "total_attendance" in cols:
        conn.execute(
            "UPDATE customers SET total_visits = CASE WHEN total_visits = 0"
            " THEN COALESCE(total_attendance, 0) ELSE total_visits END"
        )
    if "last_attendance_time" in cols:
        conn.execute(
            "UPDATE customers SET last_visit = CASE WHEN last_visit = ? THEN COALESCE(last_attendance_time, ?) "
            "ELSE last_visit END",
            (DEFAULT_TIME, DEFAULT_TIME),
        )

    # Migrate previous normalized profile table into customers
    profile_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='customer_profiles'"
    ).fetchone()
    if profile_exists:
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
                    str(data.get("service_start_year")) if data.get("service_start_year") else None,
                    data.get("customer_tenure_years"),
                    data.get("customer_tenure_years"),
                    data.get("loyalty_tier"),
                    data.get("customer_type"),
                    data.get("status"),
                    cid,
                ),
            )


def _migrate_embeddings(conn):
    """Migrate face embeddings from legacy tables / pickle files into customer_embeddings."""
    # SQLite legacy: profile table with face_embedding column
    if DB_TYPE != "postgresql":
        profile_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='customer_profiles'"
        ).fetchone()
        if profile_exists and "face_embedding" in _table_columns(conn, "customer_profiles"):
            rows = conn.execute(
                "SELECT customer_id, face_embedding, face_embedding_dim, face_embedding_model "
                "FROM customer_profiles WHERE face_embedding IS NOT NULL"
            ).fetchall()
            for row in rows:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM customer_embeddings WHERE customer_id = ? AND face_embedding = ?",
                    (str(row["customer_id"]), row["face_embedding"]),
                ).fetchone()
                count = existing[0] if existing else 0
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

    # Pickle file (EncodeFile.p)
    if not ENCODE_FILE.exists():
        return
    try:
        with open(ENCODE_FILE, "rb") as f:
            payload = pickle.load(f)
    except Exception:
        return
    if not isinstance(payload, (list, tuple)) or len(payload) != 2:
        return

    embeddings, customer_ids = payload
    for embedding, customer_id in zip(embeddings, customer_ids):
        blob, dim = _embedding_to_blob(embedding)
        if not customer_id or blob is None:
            continue

        existing = conn.execute(
            "SELECT COUNT(*) FROM customer_embeddings WHERE customer_id = ? AND face_embedding = ?",
            (str(customer_id), blob),
        ).fetchone()
        count = (
            existing["count"] if (existing and DB_TYPE == "postgresql") else (existing[0] if existing else 0)
        )
        if count > 0:
            continue

        if DB_TYPE == "postgresql":
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


# ---------------------------------------------------------------------------
# Public: ensure_schema
# ---------------------------------------------------------------------------

def ensure_schema(conn):
    """Idempotent: create tables and apply any pending migrations."""
    if DB_TYPE == "postgresql":
        _ensure_schema_postgresql(conn)
    else:
        _ensure_schema_sqlite(conn)


def _ensure_schema_postgresql(conn):
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

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
        )""")
    for col in [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS cameras TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(32) DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]:
        conn.execute(col)
    conn.execute(
        "UPDATE users SET role = COALESCE(role, CASE WHEN LOWER(username) = 'admin' THEN 'admin' ELSE 'moderator' END)"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            camera_id VARCHAR(64) PRIMARY KEY,
            display_name VARCHAR(255) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT NULL
        )""")
    for col in [
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP DEFAULT NULL",
    ]:
        conn.execute(col)

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
        )""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_camera_permissions (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            camera_id VARCHAR(64) NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
            permission VARCHAR(32) NOT NULL DEFAULT 'view',
            PRIMARY KEY (user_id, camera_id, permission)
        )""")
    _add_missing_columns(conn, "user_camera_permissions", {"permission": "VARCHAR(32) NOT NULL DEFAULT 'view'"})

    conn.execute("""
        CREATE TABLE IF NOT EXISTS camera_connections (
            connection_id VARCHAR(64) PRIMARY KEY,
            camera_id VARCHAR(64) NOT NULL REFERENCES cameras(camera_id) ON DELETE CASCADE,
            connected_at TIMESTAMP NOT NULL,
            disconnected_at TIMESTAMP DEFAULT NULL,
            disconnect_reason VARCHAR(255) DEFAULT NULL
        )""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(50) DEFAULT NULL,
            email VARCHAR(255) DEFAULT NULL,
            occupation VARCHAR(255) DEFAULT NULL,
            registered_at TIMESTAMP DEFAULT NULL,
            tenure INTEGER NOT NULL DEFAULT 0,
            loyalty_tier VARCHAR(50) NOT NULL DEFAULT 'Standard',
            total_visits INTEGER NOT NULL DEFAULT 0,
            last_visit TIMESTAMP NOT NULL DEFAULT '1970-01-01 00:00:00',
            total_spending REAL NOT NULL DEFAULT 0,
            note TEXT DEFAULT NULL,
            customer_type VARCHAR(50) NOT NULL DEFAULT 'registered',
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
    _add_missing_columns(conn, "customers", {
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "phone": "VARCHAR(50) DEFAULT NULL",
        "email": "VARCHAR(255) DEFAULT NULL",
        "occupation": "VARCHAR(255) DEFAULT NULL",
        "registered_at": "TIMESTAMP DEFAULT NULL",
        "tenure": "INTEGER NOT NULL DEFAULT 0",
        "loyalty_tier": "VARCHAR(50) NOT NULL DEFAULT 'Standard'",
        "total_visits": "INTEGER NOT NULL DEFAULT 0",
        "last_visit": "TIMESTAMP NOT NULL DEFAULT '1970-01-01 00:00:00'",
        "total_spending": "REAL NOT NULL DEFAULT 0",
        "note": "TEXT DEFAULT NULL",
        "customer_type": "VARCHAR(50) NOT NULL DEFAULT 'registered'",
        "status": "VARCHAR(50) NOT NULL DEFAULT 'active'",
    })

    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_embeddings (
            id SERIAL PRIMARY KEY,
            customer_id VARCHAR(255) NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
            face_embedding BYTEA NOT NULL,
            embedding_dim INTEGER NOT NULL DEFAULT 512,
            model_name VARCHAR(100) NOT NULL DEFAULT 'edgeface_s_gamma_05',
            created_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at VARCHAR(255) NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
    _add_missing_columns(conn, "customer_embeddings", {
        "created_at": "VARCHAR(255) DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "VARCHAR(255) DEFAULT CURRENT_TIMESTAMP",
    })
    conn.commit()

    # pgvector column + HNSW index (idempotent)
    for stmt in [
        "ALTER TABLE customer_embeddings ADD COLUMN IF NOT EXISTS embedding vector(512)",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            conn.rollback()

    for stmt in [
        "DROP INDEX IF EXISTS idx_customer_embeddings_hnsw",
        """CREATE INDEX IF NOT EXISTS idx_customer_embeddings_hnsw_halfvec
           ON customer_embeddings
           USING hnsw ((embedding::halfvec) halfvec_cosine_ops)
           WITH (m = 32, ef_construction = 128)""",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            conn.rollback()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS recognize_logs (
            id UUID DEFAULT gen_random_uuid(),
            opeid UUID NOT NULL,
            camera_id VARCHAR(255) NOT NULL,
            customer_id VARCHAR(255) DEFAULT NULL,
            track_id INTEGER DEFAULT NULL,
            bbox JSONB DEFAULT NULL,
            connection_id VARCHAR(64) DEFAULT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            moderator_username VARCHAR(255) DEFAULT 'admin',
            PRIMARY KEY (id, timestamp)
        ) PARTITION BY RANGE (timestamp);
        """)
    _add_missing_columns(conn, "recognize_logs", {"connection_id": "VARCHAR(64) DEFAULT NULL"})
    conn.commit()

    try:
        _migrate_embeddings(conn)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Embedding migration skipped: {e}")


def _ensure_schema_sqlite(conn):
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
        )""")
    _add_missing_columns(conn, "users", {
        "role": "TEXT DEFAULT NULL",
        "cameras": "TEXT DEFAULT NULL",
        "status": "TEXT NOT NULL DEFAULT 'active'",
        "created_at": "TEXT DEFAULT NULL",
        "updated_at": "TEXT DEFAULT NULL",
    })
    conn.execute(
        "UPDATE users SET role = COALESCE(role, CASE WHEN LOWER(username) = 'admin' THEN 'admin' ELSE 'moderator' END)"
    )
    conn.execute("UPDATE users SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP)")
    conn.execute("UPDATE users SET updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            camera_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT DEFAULT NULL
        )""")

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
        )""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_camera_permissions (
            user_id INTEGER NOT NULL,
            camera_id TEXT NOT NULL,
            permission TEXT NOT NULL DEFAULT 'view',
            PRIMARY KEY (user_id, camera_id, permission),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        )""")
    _add_missing_columns(conn, "user_camera_permissions", {"permission": "TEXT NOT NULL DEFAULT 'view'"})

    conn.execute("""
        CREATE TABLE IF NOT EXISTS camera_connections (
            connection_id TEXT PRIMARY KEY,
            camera_id TEXT NOT NULL,
            connected_at TEXT NOT NULL,
            disconnected_at TEXT DEFAULT NULL,
            disconnect_reason TEXT DEFAULT NULL,
            FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        )""")

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
        )""")
    _add_missing_columns(conn, "customers", {
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
    })

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
        )""")

    # Migration: ensure 'id' column exists
    columns = _table_columns(conn, "customer_embeddings")
    if "id" not in columns:
        conn.execute("ALTER TABLE customer_embeddings RENAME TO customer_embeddings_old")
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
            )""")
        conn.execute("""
            INSERT INTO customer_embeddings (customer_id, face_embedding, embedding_dim, model_name, created_at, updated_at)
            SELECT customer_id, face_embedding, embedding_dim, model_name, created_at, updated_at
            FROM customer_embeddings_old
            """)
        conn.execute("DROP TABLE customer_embeddings_old")

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
        )""")
    _add_missing_columns(conn, "recognize_logs", {"connection_id": "TEXT DEFAULT NULL"})

    _migrate_legacy_customer_data(conn)
    _migrate_embeddings(conn)
    _add_all_audit_columns(conn)
    conn.commit()
