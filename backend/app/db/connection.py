import sqlite3
from datetime import datetime

from config import DB_PATH


CUSTOMER_COLUMNS = {
    "id": "TEXT PRIMARY KEY",
    "name": "TEXT NOT NULL",
    "major": "TEXT NOT NULL DEFAULT 'Unknown'",
    "starting_year": "INTEGER NOT NULL DEFAULT 0",
    "total_attendance": "INTEGER NOT NULL DEFAULT 0",
    "standing": "TEXT NOT NULL DEFAULT 'G'",
    "year": "INTEGER NOT NULL DEFAULT 0",
    "last_attendance_time": "TEXT NOT NULL DEFAULT '1970-01-01 00:00:00'",
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
                name TEXT NOT NULL,
                major TEXT NOT NULL DEFAULT 'Unknown',
                starting_year INTEGER NOT NULL DEFAULT 0,
                total_attendance INTEGER NOT NULL DEFAULT 0,
                standing TEXT NOT NULL DEFAULT 'G',
                year INTEGER NOT NULL DEFAULT 0,
                last_attendance_time TEXT NOT NULL DEFAULT '1970-01-01 00:00:00'
            )
            """
        )
        conn.commit()
        return

    for column_name, column_definition in CUSTOMER_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE customers ADD COLUMN {column_name} {column_definition}")

    if {"visit_count", "last_visit"} & existing_columns:
        conn.execute(
            """
            UPDATE customers
            SET
                total_attendance = COALESCE(total_attendance, visit_count, 0),
                last_attendance_time = COALESCE(last_attendance_time, last_visit, '1970-01-01 00:00:00'),
                major = COALESCE(NULLIF(major, ''), 'Unknown'),
                starting_year = COALESCE(starting_year, 0),
                standing = COALESCE(NULLIF(standing, ''), 'G'),
                year = COALESCE(year, 0)
            """
        )

    conn.commit()


def get_customer_info(conn, customer_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, major, starting_year, total_attendance, standing, year, last_attendance_time
        FROM customers WHERE id = ?
        """,
        (customer_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def update_attendance(conn, customer_id, total_attendance, last_attendance_time):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE customers
        SET total_attendance = ?, last_attendance_time = ?
        WHERE id = ?
        """,
        (total_attendance, last_attendance_time, customer_id),
    )
    conn.commit()


def upsert_customer(
    conn,
    customer_id,
    name,
    major,
    starting_year,
    total_attendance,
    standing,
    year,
    last_attendance_time,
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO customers (
            id, name, major, starting_year, total_attendance, standing, year, last_attendance_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            name,
            major,
            starting_year,
            total_attendance,
            standing,
            year,
            last_attendance_time,
        ),
    )
    conn.commit()


def insert_guest_record(conn, guest_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    upsert_customer(
        conn,
        guest_id,
        "Guest",
        "Guest",
        0,
        0,
        "G",
        0,
        now,
    )
