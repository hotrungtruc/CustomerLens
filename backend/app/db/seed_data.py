from app.db.connection import ensure_schema, get_db_connection

DATA = {
    "000": {
        "name": "Truong Quoc Tri",
        "phone": None,
        "visit_count": 1,
        "last_visit": "2026-05-22 00:00:00",
    },
    "001": {
        "name": "Pham Phu Nhat Quang",
        "phone": None,
        "visit_count": 1,
        "last_visit": "2022-12-11 00:54:34",
    },
    "002": {
        "name": "Dau Phuc Duc",
        "phone": None,
        "visit_count": 1,
        "last_visit": "2022-12-11 00:54:34",
    },
    "003": {
        "name": "Ho Trung Truc",
        "phone": None,
        "visit_count": 1,
        "last_visit": "2022-12-11 00:54:34",
    },
    "004": {
        "name": "Lebron James",
        "phone": None,
        "visit_count": 1,
        "last_visit": "2026-05-22 00:00:00",
    },
    "006": {
        "name": "Amen Thompson",
        "phone": None,
        "visit_count": 1,
        "last_visit": "2026-05-22 00:00:00",
    },
    "007": {
        "name": "Ausar Thompson",
        "phone": None,
        "visit_count": 1,
        "last_visit": "2026-05-22 00:00:00",
    },
}


def main():
    conn = get_db_connection()
    ensure_schema(conn)

    for key, value in DATA.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO customers (
                id, name, phone, visit_count, last_visit
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                value["name"],
                value["phone"],
                value["visit_count"],
                value["last_visit"],
            ),
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
