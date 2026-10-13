"""
Customer repository: CRUD, embeddings, attendance updates.
"""

import re
from datetime import datetime

from db_config import DB_TYPE

DEFAULT_TIME = "1970-01-01 00:00:00"
DEFAULT_MODEL = "edgeface_s_gamma_05"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_next_customer_id(conn) -> str:
    rows = conn.execute("SELECT customer_id FROM customers").fetchall()
    max_numeric = -1
    for row in rows:
        value = str(row["customer_id"] or "")
        if re.fullmatch(r"\d+", value):
            max_numeric = max(max_numeric, int(value))
    return f"{max_numeric + 1:03d}"


def _row_to_customer(row):
    """Normalise a DB row to a customer dict with backward-compatible aliases."""
    if not row:
        return None
    data = dict(row)
    data.setdefault("id", data.get("customer_id"))
    data.setdefault("service_category", "General")
    data.setdefault("service_start_year", data.get("registered_at"))
    data.setdefault("customer_tenure_years", data.get("tenure"))
    data.setdefault("major", "")
    data.setdefault("starting_year", data.get("registered_at"))
    data.setdefault("year", data.get("tenure"))
    data.setdefault("standing", data.get("loyalty_tier"))
    data.setdefault("total_attendance", data.get("total_visits", 0))
    data.setdefault("last_attendance_time", data.get("last_visit"))
    data.setdefault("visit_count", data.get("total_visits", 0))
    data.setdefault("last_visit", data.get("last_visit"))
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_customer_info(conn, customer_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.customer_id, c.name, c.phone, c.email, c.registered_at,
            c.tenure, c.loyalty_tier, c.total_visits, c.last_visit, c.total_spending,
            c.note, c.customer_type, c.status, c.created_at, c.updated_at,
            CASE WHEN e.customer_id IS NULL THEN 0 ELSE 1 END AS has_face_embedding,
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
    registered_at=None,
    tenure=None,
    loyalty_tier=None,
    service_category=None,
    service_start_year=None,
    customer_tenure_years=None,
    **legacy_kwargs,
):
    clean_id = (customer_id or "").strip()
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Customer name is required")

    # Field aliases
    registered_at = registered_at if registered_at is not None else service_start_year
    tenure = tenure if tenure is not None else customer_tenure_years

    if (
        clean_id.startswith("T")
        or clean_id.startswith("GUEST_")
        or clean_id.startswith("test_")
        or clean_id.startswith("LN")
    ):
        clean_id = ""

    existing = get_customer_info(conn, clean_id) if clean_id else None
    final_id = clean_id or _generate_next_customer_id(conn)
    created = existing is None

    if created:
        conn.execute(
            """
            INSERT INTO customers (
                customer_id, name, phone, email, registered_at,
                tenure, loyalty_tier, note, customer_type, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'registered', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                final_id,
                clean_name,
                phone,
                email,
                registered_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                int(tenure or 0),
                loyalty_tier or "Standard",
                note,
            ),
        )
    else:
        conn.execute(
            "UPDATE customers SET name = ?, phone = ?, note = ?, updated_at = CURRENT_TIMESTAMP WHERE customer_id = ?",
            (clean_name, phone, note, final_id),
        )
    conn.commit()
    return final_id, created


def upsert_customer(
    conn,
    customer_id,
    name,
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
    """Upsert a customer record, accepting legacy field names via kwargs."""
    registered_at = legacy_kwargs.get("service_start_year", registered_at)
    tenure = legacy_kwargs.get("customer_tenure_years", tenure)
    total_visits = legacy_kwargs.get("total_attendance", total_visits)
    last_visit = legacy_kwargs.get("last_attendance_time", last_visit)

    if isinstance(registered_at, int):
        registered_at = f"{registered_at:04d}-01-01 00:00:00"
    elif isinstance(registered_at, str) and len(registered_at) == 4 and registered_at.isdigit():
        registered_at = f"{registered_at}-01-01 00:00:00"

    conn.execute(
        """
        INSERT INTO customers (
            customer_id, name, phone, email, registered_at, tenure,
            loyalty_tier, total_visits, last_visit, total_spending, note,
            customer_type, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(customer_id) DO UPDATE SET
            name = excluded.name,
            phone = excluded.phone,
            email = excluded.email,
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
            customer_id, name, phone, email,
            str(registered_at or DEFAULT_TIME),
            int(tenure or 0),
            loyalty_tier or "Standard",
            int(total_visits or 0),
            last_visit or DEFAULT_TIME,
            float(total_spending or 0),
            note, customer_type, status,
        ),
    )
    conn.commit()


def insert_guest_record(conn, guest_id):
    upsert_customer(
        conn,
        guest_id,
        "Guest",
        registered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_visits=0,
        loyalty_tier="Standard",
        tenure=0,
        last_visit=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        customer_type="guest",
        status="temporary",
    )


def update_attendance(conn, customer_id, total_attendance=None, last_attendance_time=None):
    event_time = last_attendance_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    next_total = total_attendance
    if next_total is None:
        current = get_customer_info(conn, customer_id) or {}
        next_total = int(current.get("total_visits") or 0) + 1
    conn.execute(
        "UPDATE customers SET total_visits = ?, last_visit = ?, updated_at = CURRENT_TIMESTAMP WHERE customer_id = ?",
        (int(next_total or 0), event_time, customer_id),
    )
    conn.commit()
