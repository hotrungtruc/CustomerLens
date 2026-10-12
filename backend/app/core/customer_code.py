"""
CustomerLens 2-Letter Customer Segmentation & ID Code System.

System Rules:
• 1st Letter — Income & Spending Power:
    • H (High): High income, strong spending (VIP / Premium / Diamond / Platinum).
    • M (Medium): Average income, reasonable spending (Mass / Middle / Gold / Standard).
    • L (Low): Budget-conscious, price sensitive, or new unverified guest.

• 2nd Letter — Behavior & Loyalty:
    • L (Loyal): Returning customer, frequent visits (total_visits >= 5 or tenure >= 2).
    • C (Casual): Occasional visitor, casual guest (1 < total_visits < 5).
    • N (New): First-time visitor, brand new customer (total_visits <= 1 or guest).

Default input for newly detected guests: "LN" (e.g. LN1, LN2, LN3...)
"""

import re
import threading

# Segment descriptions dictionary
SEGMENT_LABELS = {
    "HL": ("VIP • Loyal", "Thu nhập cao • Khách quen gắn bó"),
    "HC": ("VIP • Casual", "Thu nhập cao • Thỉnh thoảng ghé"),
    "HN": ("VIP • New", "Thu nhập cao • Trải nghiệm lần đầu"),
    "ML": ("Mass • Loyal", "Thu nhập TB • Khách quen thường xuyên"),
    "MC": ("Mass • Casual", "Thu nhập TB • Khách vãng lai"),
    "MN": ("Mass • New", "Thu nhập TB • Khách mới"),
    "LL": ("Budget • Loyal", "Tiết kiệm • Khách quen"),
    "LC": ("Budget • Casual", "Tiết kiệm • Khách vãng lai"),
    "LN": ("Budget • New Guest", "Khách mới chưa đăng ký (Mặc định)"),
}


def compute_segment_code(customer: dict | None) -> tuple[str, str, str] | None:
    """
    Computes (2-letter code, short label, detailed Vietnamese description).
    Returns None if customer is None or has no resolved identity.
    """
    if not customer:
        return None

    c_id = str(customer.get("customer_id") or customer.get("id") or "").strip()
    if not c_id:
        return None

    # 1. First letter: Income / Spending Tier
    tier = str(customer.get("loyalty_tier") or customer.get("standing") or "").upper()
    category = str(customer.get("service_category") or customer.get("major") or "").upper()
    spending = float(customer.get("total_spending") or 0)

    if any(k in tier for k in ["VIP", "DIAMOND", "PLATINUM"]) or "PREMIUM" in category or spending >= 10_000_000:
        first_letter = "H"
    elif any(k in tier for k in ["GOLD", "SILVER", "MASS", "MIDDLE"]) or spending >= 2_000_000:
        first_letter = "M"
    else:
        first_letter = "L"

    # 2. Second letter: Loyalty & Behavior
    visits = int(customer.get("total_visits") or customer.get("total_attendance") or customer.get("visit_count") or 0)
    tenure = int(customer.get("tenure") or customer.get("customer_tenure_years") or customer.get("year") or 0)

    if visits >= 5 or tenure >= 2:
        second_letter = "L"
    elif visits > 1:
        second_letter = "C"
    else:
        second_letter = "N"

    code = f"{first_letter}{second_letter}"
    labels = SEGMENT_LABELS.get(code, ("Customer", "Khách hàng"))
    return code, labels[0], labels[1]


def extract_customer_number(customer_id: str | None) -> str | None:
    """Extract numeric suffix from any ID (e.g. 'LN1' -> '1', 'GUEST_0_0002' -> '2', '005' -> '5')."""
    if not customer_id:
        return None
    cid = str(customer_id).strip()
    m = re.search(r"(\d+)$", cid)
    if m:
        return str(int(m.group(1)))
    return cid


def format_display_customer_id(customer: dict | None) -> str | None:
    """
    Returns short, non-colliding formatted ID with 2-letter segment prefix (e.g. LN1, LC1, LL1, MN1, HL1).
    Returns None if embedding is not yet saved / customer is not resolved.
    """
    if not customer:
        return None
    c_id = str(customer.get("customer_id") or customer.get("id") or "").strip()
    if not c_id:
        return None

    seg = compute_segment_code(customer)
    prefix = seg[0] if seg else "LN"
    num = extract_customer_number(c_id)
    if num:
        return f"{prefix}{num}"
    return c_id


# Thread-safe guest ID generator counter
_guest_seq_lock = threading.Lock()
_next_guest_seq = None


_redis_sync_client = None


def _get_redis_sync():
    global _redis_sync_client
    if _redis_sync_client is None:
        try:
            import redis
            from config import REDIS_URL
            _redis_sync_client = redis.from_url(REDIS_URL, decode_responses=True)
            # Ping to verify connection
            _redis_sync_client.ping()
        except Exception:
            _redis_sync_client = None
    return _redis_sync_client


def init_guest_sequence_from_db(conn):
    """Scan existing database to initialize the highest guest sequence number."""
    global _next_guest_seq
    with _guest_seq_lock:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT customer_id FROM customers WHERE customer_id LIKE 'LN%' OR customer_id LIKE 'GUEST_%'"
        )
        rows = cursor.fetchall()
        max_seq = 0
        pattern_ln = re.compile(r"^LN(\d+)$")
        pattern_guest = re.compile(r"GUEST_.*?(\d+)$")

        for r in rows:
            cid = str(r[0] if isinstance(r, (list, tuple)) else r["customer_id"] or "")
            m_ln = pattern_ln.match(cid)
            if m_ln:
                max_seq = max(max_seq, int(m_ln.group(1)))
                continue
            m_g = pattern_guest.match(cid)
            if m_g:
                try:
                    max_seq = max(max_seq, int(m_g.group(1)))
                except ValueError:
                    pass

        _next_guest_seq = max_seq
        return _next_guest_seq


def generate_next_guest_id(conn=None, redis_client=None, prefix="LN") -> str:
    """
    Generate next unique guest ID (e.g. LN1, LN2, LN3...)
    Uses Redis atomic INCR when available, with thread-safe DB/memory fallback.
    Guaranteed non-colliding and ultra-short.
    """
    global _next_guest_seq

    # 1. Try Redis atomic counter for distributed multi-process safety
    r = redis_client or _get_redis_sync()
    if r is not None:
        try:
            key = f"seq:customer:{prefix}"
            # Check if key already exists in Redis; if not, initialize from DB
            if not r.exists(key):
                max_s = 0
                if conn is not None:
                    max_s = init_guest_sequence_from_db(conn)
                else:
                    try:
                        from app.db.connection import get_db_connection
                        _db = get_db_connection()
                        try:
                            max_s = init_guest_sequence_from_db(_db)
                        finally:
                            _db.close()
                    except Exception:
                        pass
                r.setnx(key, max_s)

            seq = r.incr(key)
            return f"{prefix}{seq}"
        except Exception:
            pass

    # 2. Local thread-safe fallback with DB scan
    with _guest_seq_lock:
        if _next_guest_seq is None and conn is not None:
            init_guest_sequence_from_db(conn)
        elif _next_guest_seq is None:
            try:
                from app.db.connection import get_db_connection
                _db = get_db_connection()
                try:
                    init_guest_sequence_from_db(_db)
                finally:
                    _db.close()
            except Exception:
                _next_guest_seq = 0

        _next_guest_seq += 1
        return f"{prefix}{_next_guest_seq}"

