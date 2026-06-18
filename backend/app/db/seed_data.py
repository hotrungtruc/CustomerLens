import hashlib
from app.db.connection import ensure_schema, get_db_connection, upsert_customer

# Demo customer data for the school project.
# The old academic-like fields were renamed for store/customer semantics:
# - major -> service_category: group/service/product category related to customer
# - starting_year -> service_start_year: year customer started using the store/service
# - year -> customer_tenure_years: customer seniority/relationship length in years
# - standing -> loyalty_tier: customer tier/rank
DATA = {
    "000": {
        "name": "Truong Quoc Tri",
        "service_category": "Education partner",
        "service_start_year": 2020,
        "customer_tenure_years": 6,
        "loyalty_tier": "VIP",
        "total_attendance": 0,
        "last_attendance_time": "2026-05-22 00:00:00",
        "phone": None,
        "note": "Demo customer profile",
    },
    "001": {
        "name": "Pham Phu Nhat Quang",
        "service_category": "Technology services",
        "service_start_year": 2023,
        "customer_tenure_years": 3,
        "loyalty_tier": "Standard",
        "total_attendance": 0,
        "last_attendance_time": "2022-12-11 00:54:34",
        "phone": None,
        "note": "Team member test profile",
    },
    "002": {
        "name": "Dau Phuc Duc",
        "service_category": "Software services",
        "service_start_year": 2023,
        "customer_tenure_years": 3,
        "loyalty_tier": "Standard",
        "total_attendance": 0,
        "last_attendance_time": "2022-12-11 00:54:34",
        "phone": None,
        "note": "Team member test profile",
    },
    "003": {
        "name": "Ho Trung Truc",
        "service_category": "Computer services",
        "service_start_year": 2023,
        "customer_tenure_years": 3,
        "loyalty_tier": "Standard",
        "total_attendance": 0,
        "last_attendance_time": "2022-12-11 00:54:34",
        "phone": None,
        "note": "Team member test profile",
    },
    "004": {
        "name": "Lebron James",
        "service_category": "Premium retail",
        "service_start_year": 2003,
        "customer_tenure_years": 23,
        "loyalty_tier": "VIP",
        "total_attendance": 0,
        "last_attendance_time": "2026-05-22 00:00:00",
        "phone": None,
        "note": "External demo customer",
    },
    "006": {
        "name": "Amen Thompson",
        "service_category": "Premium retail",
        "service_start_year": 2023,
        "customer_tenure_years": 3,
        "loyalty_tier": "Gold",
        "total_attendance": 0,
        "last_attendance_time": "2026-05-22 00:00:00",
        "phone": None,
        "note": "External demo customer",
    },
    "007": {
        "name": "Ausar Thompson",
        "service_category": "Premium retail",
        "service_start_year": 2023,
        "customer_tenure_years": 3,
        "loyalty_tier": "Gold",
        "total_attendance": 0,
        "last_attendance_time": "2026-05-22 00:00:00",
        "phone": None,
        "note": "External demo customer",
    },
}


def main():
    conn = get_db_connection()
    ensure_schema(conn)

    for customer_id, value in DATA.items():
        upsert_customer(
            conn,
            customer_id=customer_id,
            name=value["name"],
            service_category=value["service_category"],
            service_start_year=value["service_start_year"],
            customer_tenure_years=value["customer_tenure_years"],
            loyalty_tier=value["loyalty_tier"],
            total_attendance=value["total_attendance"],
            last_attendance_time=value["last_attendance_time"],
            phone=value.get("phone"),
            note=value.get("note"),
            customer_type="registered",
            status="active",
        )

    # Seed default user accounts
    default_users = [
        ("admin", "admin123", "admin", None),
        ("moderator", "mod123", "moderator", "DSLR-002,DSLR-003")
    ]
    for username, password, role, cameras in default_users:
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        # Clean existing user if conflict
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, cameras)
            VALUES (?, ?, ?, ?)
            """,
            (username, pwd_hash, role, cameras)
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
