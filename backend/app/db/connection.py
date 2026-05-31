import sqlite3
from datetime import datetime

from config import DB_PATH


CUSTOMER_COLUMNS = {
    "id": "TEXT PRIMARY KEY",
    "name": "TEXT DEFAULT NULL",
    "phone": "TEXT DEFAULT NULL",
    "visit_count": "INTEGER NOT NULL DEFAULT 1",
    "last_visit": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
}


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn):
    cursor = conn.execute("PRAGMA table_info(customers)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if not existing_columns:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT DEFAULT NULL,
                phone TEXT DEFAULT NULL,
                visit_count INTEGER NOT NULL DEFAULT 1,
                last_visit TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        return

    if {"id", "name", "phone", "visit_count", "last_visit"} <= existing_columns:
        conn.execute("""
            UPDATE customers
            SET
                name = NULLIF(name, ''),
                phone = NULLIF(phone, ''),
                visit_count = COALESCE(visit_count, 1),
                last_visit = COALESCE(last_visit, CURRENT_TIMESTAMP)
        """)
        conn.commit()
        return

    conn.execute("ALTER TABLE customers RENAME TO customers_legacy")
    conn.execute(
        """
        CREATE TABLE customers (
            id TEXT PRIMARY KEY,
            name TEXT DEFAULT NULL,
            phone TEXT DEFAULT NULL,
            visit_count INTEGER NOT NULL DEFAULT 1,
            last_visit TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    legacy_columns = {row[1] for row in conn.execute("PRAGMA table_info(customers_legacy)").fetchall()}
    if {"visit_count", "last_visit"} <= legacy_columns:
        conn.execute(
            """
            INSERT INTO customers (id, name, phone, visit_count, last_visit)
            SELECT
                id,
                NULLIF(name, ''),
                NULLIF(phone, ''),
                COALESCE(visit_count, total_attendance, 1),
                COALESCE(last_visit, last_attendance_time, CURRENT_TIMESTAMP)
            FROM customers_legacy
            """
        )
    else:
        conn.execute(
            """
            INSERT INTO customers (id, name, phone, visit_count, last_visit)
            SELECT
                id,
                NULLIF(name, ''),
                NULL,
                COALESCE(total_attendance, 1),
                COALESCE(last_attendance_time, CURRENT_TIMESTAMP)
            FROM customers_legacy
            """
        )

    conn.execute("DROP TABLE customers_legacy")
    conn.commit()


def get_customer_info(conn, customer_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, phone, visit_count, last_visit
        FROM customers WHERE id = ?
        """,
        (customer_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def update_visit_record(conn, customer_id, visit_count, last_visit):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE customers
        SET visit_count = ?, last_visit = ?
        WHERE id = ?
        """,
        (visit_count, last_visit, customer_id),
    )
    conn.commit()


def upsert_customer(
    conn,
    customer_id,
    name,
    phone,
    visit_count,
    last_visit,
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO customers (
            id, name, phone, visit_count, last_visit
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            name,
            phone,
            visit_count,
            last_visit,
        ),
    )
    conn.commit()


def insert_guest_record(conn, guest_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    upsert_customer(
        conn,
        guest_id,
        None,
        None,
        1,
        now,
    )
