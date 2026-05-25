import sqlite3
import os

# ✅ FIX: Get the project root directory (one level up from src/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ✅ Set working directory to project root
os.chdir(PROJECT_ROOT)

# ✅ Use absolute path for database
DB_PATH = os.path.join(PROJECT_ROOT, "face_attendance.db")


def ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
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


data = {
    "000": {
        "name": "Truong Quoc Tri",
        "major": "Lecturer - Van Lang University",
        "starting_year": 2020,
        "total_attendance": 0,
        "standing": "G",
        "year": 0,
        "last_attendance_time": "2026-05-22 00:00:00",
    },
    "001": {
        "name": "Pham Phu Nhat Quang",
        "major": "Information Technology",
        "starting_year": 2023,
        "total_attendance": 0,
        "standing": "G",
        "year": 2,
        "last_attendance_time": "2022-12-11 00:54:34",
    },
    "002": {
        "name": "Dau Phuc Duc",
        "major": "Software Engineering",
        "starting_year": 2023,
        "total_attendance": 0,
        "standing": "G",
        "year": 2,
        "last_attendance_time": "2022-12-11 00:54:34",
    },
    "003": {
        "name": "Ho Trung Truc",
        "major": "Computer Science",
        "starting_year": 2023,
        "total_attendance": 0,
        "standing": "G",
        "year": 2,
        "last_attendance_time": "2022-12-11 00:54:34",
    },
    "004": {
        "name": "Lebron James",
        "major": "Professional NBA Player",
        "starting_year": 2003,
        "total_attendance": 0,
        "standing": "G",
        "year": 0,
        "last_attendance_time": "2026-05-22 00:00:00",
    },
}

conn = sqlite3.connect(DB_PATH)
ensure_schema(conn)

for key, value in data.items():
    conn.execute(
        """
        INSERT OR REPLACE INTO students (
            id, name, major, starting_year, total_attendance, standing, year, last_attendance_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            value["name"],
            value["major"],
            value["starting_year"],
            value["total_attendance"],
            value["standing"],
            value["year"],
            value["last_attendance_time"],
        ),
    )

conn.commit()
conn.close()
