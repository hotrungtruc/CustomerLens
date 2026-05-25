from app.db.connection import ensure_schema, get_db_connection

DATA = {
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
    "006": {
        "name": "Amen Thompson",
        "major": "Professional NBA Player",
        "starting_year": 2003,
        "total_attendance": 0,
        "standing": "G",
        "year": 0,
        "last_attendance_time": "2026-05-22 00:00:00",
    },
    "007": {
        "name": "Ausar Thompson",
        "major": "Professional NBA Player",
        "starting_year": 2003,
        "total_attendance": 0,
        "standing": "G",
        "year": 0,
        "last_attendance_time": "2026-05-22 00:00:00",
    },
}


def main():
    conn = get_db_connection()
    ensure_schema(conn)

    for key, value in DATA.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO customers (
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


if __name__ == "__main__":
    main()
