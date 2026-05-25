import sqlite3

from config import DB_PATH


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            major TEXT NOT NULL,
            starting_year INTEGER NOT NULL,
            total_attendance INTEGER NOT NULL,
            standing TEXT NOT NULL,
            year INTEGER NOT NULL,
            last_attendance_time TEXT NOT NULL
        )
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
