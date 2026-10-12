"""
Logs & analytics repository:
  - bulk_insert_recognize_logs
  - get_recognize_logs
  - get_reports_data
"""

import json
import uuid
from datetime import datetime

import psycopg2.extras
from db_config import DB_TYPE


def bulk_insert_recognize_logs(conn, logs):
    """
    Bulk-insert recognition log rows.

    Each item in `logs` must contain:
        opeid, camera_id, connection_id, customer_id, track_id, bbox, timestamp
    """
    if not logs:
        return

    if DB_TYPE == "postgresql":
        pg_conn = conn.conn
        cursor = pg_conn.cursor()
        query = """
            INSERT INTO recognize_logs (id, opeid, camera_id, connection_id, customer_id, track_id, bbox, timestamp)
            VALUES %s
        """
        values = []
        for log in logs:
            bbox_val = json.dumps(log.get("bbox")) if log.get("bbox") else None
            ts = log.get("timestamp", datetime.now())
            try:
                track_val = int(log["track_id"]) if log.get("track_id") is not None else None
            except (ValueError, TypeError):
                track_val = None
            values.append((
                str(uuid.uuid4()),
                str(log["opeid"]),
                str(log["camera_id"]),
                str(log["connection_id"]) if log.get("connection_id") else None,
                str(log["customer_id"]) if log.get("customer_id") else None,
                track_val,
                bbox_val,
                ts,
            ))
        try:
            psycopg2.extras.execute_values(cursor, query, values)
            pg_conn.commit()
        except Exception as e:
            pg_conn.rollback()
            print(f"Bulk insert recognize logs failed: {e}")
        finally:
            cursor.close()
    else:
        query = """
            INSERT INTO recognize_logs (id, opeid, camera_id, connection_id, customer_id, track_id, bbox, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = []
        for log in logs:
            bbox_val = json.dumps(log.get("bbox")) if log.get("bbox") else None
            ts = log.get("timestamp", datetime.now().isoformat())
            if isinstance(ts, datetime):
                ts = ts.isoformat()
            try:
                track_val = int(log["track_id"]) if log.get("track_id") is not None else None
            except (ValueError, TypeError):
                track_val = None
            values.append((
                str(uuid.uuid4()),
                str(log["opeid"]),
                str(log["camera_id"]),
                str(log["connection_id"]) if log.get("connection_id") else None,
                str(log["customer_id"]) if log.get("customer_id") else None,
                track_val,
                bbox_val,
                ts,
            ))
        try:
            conn.executemany(query, values)
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"Bulk insert recognize logs failed: {e}")


def get_recognize_logs(
    conn,
    start_date=None,
    end_date=None,
    camera_id=None,
    customer_type=None,
    search=None,
    limit=50,
    offset=0,
):
    """
    Return paginated recognition logs joined with customer and camera details.
    Supports filtering by date range, camera, customer type, and free-text search.
    """
    where_clauses = []
    params = []

    if start_date:
        where_clauses.append("rl.timestamp >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("rl.timestamp <= ?")
        params.append(end_date)
    if camera_id and camera_id != "all":
        where_clauses.append("rl.camera_id = ?")
        params.append(camera_id)
    if customer_type and customer_type != "all":
        if customer_type == "guest":
            where_clauses.append("(c.customer_type = 'guest' OR c.customer_type IS NULL OR c.customer_type = 'temporary')")
        elif customer_type in ["registered", "customer", "vip"]:
            where_clauses.append("(c.customer_type != 'guest' AND c.customer_type != 'temporary' AND c.customer_type IS NOT NULL)")
        else:
            where_clauses.append("c.customer_type = ?")
            params.append(customer_type)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        where_clauses.append("(c.name LIKE ? OR c.phone LIKE ? OR rl.customer_id LIKE ? OR rl.camera_id LIKE ?)")
        params.extend([pattern, pattern, pattern, pattern])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_row = conn.execute(
        f"SELECT COUNT(*) as total FROM recognize_logs rl LEFT JOIN customers c ON rl.customer_id = c.customer_id {where_sql}",
        tuple(params),
    ).fetchone()
    total_count = count_row["total"] if isinstance(count_row, dict) else (count_row[0] if count_row else 0)

    data_query = f"""
        SELECT
            rl.id, rl.opeid, rl.camera_id,
            cam.display_name as camera_name,
            rl.customer_id,
            c.name as customer_name,
            c.phone as customer_phone,
            c.customer_type,
            c.loyalty_tier,
            rl.track_id, rl.bbox, rl.timestamp
        FROM recognize_logs rl
        LEFT JOIN customers c ON rl.customer_id = c.customer_id
        LEFT JOIN cameras cam ON rl.camera_id = cam.camera_id
        {where_sql}
        ORDER BY rl.timestamp DESC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(data_query, tuple(params) + (int(limit), int(offset))).fetchall()

    logs = []
    for r in rows:
        item = dict(r) if hasattr(r, "keys") else {
            "id": r[0], "opeid": r[1], "camera_id": r[2], "camera_name": r[3],
            "customer_id": r[4], "customer_name": r[5], "customer_phone": r[6],
            "customer_type": r[7], "loyalty_tier": r[8], "track_id": r[9],
            "bbox": r[10], "timestamp": str(r[11]),
        }
        cid = item.get("customer_id")
        is_guest = not cid or str(cid).startswith("GUEST_") or str(cid).startswith("LN")
        if not item.get("customer_name"):
            item["customer_name"] = "Khách mới" if is_guest else (cid or "Khách hàng")
        if not item.get("customer_type"):
            item["customer_type"] = "guest" if is_guest else "customer"
        if not item.get("camera_name"):
            item["camera_name"] = item.get("camera_id") or "Camera Sảnh"
        logs.append(item)

    return {"logs": logs, "total_count": total_count}


def get_reports_data(conn, start_date=None, end_date=None, camera_id=None):
    """
    Compute analytics: summary KPIs, hourly/daily traffic, loyalty distribution, top customers.
    """
    where_clauses = []
    params = []
    if start_date:
        where_clauses.append("rl.timestamp >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("rl.timestamp <= ?")
        params.append(end_date)
    if camera_id and camera_id != "all":
        where_clauses.append("rl.camera_id = ?")
        params.append(camera_id)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # 1. Summary KPIs
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) as total_visits,
            SUM(CASE WHEN c.customer_type IS NOT NULL AND c.customer_type NOT IN ('guest', 'temporary') THEN 1 ELSE 0 END) as vip_visits,
            SUM(CASE WHEN c.customer_type IS NULL OR c.customer_type IN ('guest', 'temporary') THEN 1 ELSE 0 END) as guest_visits,
            COUNT(DISTINCT rl.customer_id) as unique_customers
        FROM recognize_logs rl LEFT JOIN customers c ON rl.customer_id = c.customer_id {where_sql}
        """,
        tuple(params),
    ).fetchone()
    total_visits   = (row["total_visits"]   if isinstance(row, dict) else row[0] if row else 0) or 0
    vip_visits     = (row["vip_visits"]     if isinstance(row, dict) else row[1] if row else 0) or 0
    guest_visits   = (row["guest_visits"]   if isinstance(row, dict) else row[2] if row else 0) or 0
    unique_customers = (row["unique_customers"] if isinstance(row, dict) else row[3] if row else 0) or 0
    repeat_rate = round(vip_visits / total_visits * 100, 1) if total_visits > 0 else 0.0

    # 2. Hourly distribution
    if DB_TYPE == "postgresql":
        hourly_sql = f"SELECT EXTRACT(HOUR FROM rl.timestamp)::int as hr, COUNT(*) as count FROM recognize_logs rl LEFT JOIN customers c ON rl.customer_id = c.customer_id {where_sql} GROUP BY hr ORDER BY hr"
    else:
        hourly_sql = f"SELECT CAST(strftime('%H', rl.timestamp) AS INTEGER) as hr, COUNT(*) as count FROM recognize_logs rl LEFT JOIN customers c ON rl.customer_id = c.customer_id {where_sql} GROUP BY hr ORDER BY hr"
    hourly_map = {h: 0 for h in range(24)}
    for r in conn.execute(hourly_sql, tuple(params)).fetchall():
        hr  = r["hr"]    if isinstance(r, dict) else r[0]
        cnt = r["count"] if isinstance(r, dict) else r[1]
        if hr is not None and 0 <= hr < 24:
            hourly_map[hr] = cnt
    hourly_data = [{"hour": f"{h}h", "count": hourly_map[h]} for h in range(8, 22)]
    peak_hour_item = max(hourly_data, key=lambda x: x["count"]) if hourly_data else {"hour": "12h", "count": 0}

    # 3. Daily traffic (last 7 days)
    if DB_TYPE == "postgresql":
        daily_sql = f"SELECT TO_CHAR(rl.timestamp, 'YYYY-MM-DD') as day_str, COUNT(*) as count FROM recognize_logs rl LEFT JOIN customers c ON rl.customer_id = c.customer_id {where_sql} GROUP BY day_str ORDER BY day_str DESC LIMIT 7"
    else:
        daily_sql = f"SELECT DATE(rl.timestamp) as day_str, COUNT(*) as count FROM recognize_logs rl LEFT JOIN customers c ON rl.customer_id = c.customer_id {where_sql} GROUP BY day_str ORDER BY day_str DESC LIMIT 7"
    daily_rows = conn.execute(daily_sql, tuple(params)).fetchall()
    daily_data = [
        {"day": str((r["day_str"] if isinstance(r, dict) else r[0]) or ""), "count": (r["count"] if isinstance(r, dict) else r[1])}
        for r in reversed(daily_rows)
    ]
    if not daily_data:
        daily_data = [{"day": d, "count": 0} for d in ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]]

    # 4. Loyalty distribution
    loyalty_rows = conn.execute(
        f"SELECT COALESCE(c.loyalty_tier, 'Guest') as tier, COUNT(*) as count FROM recognize_logs rl LEFT JOIN customers c ON rl.customer_id = c.customer_id {where_sql} GROUP BY tier",
        tuple(params),
    ).fetchall()
    loyalty_data = [
        {"tier": (r["tier"] if isinstance(r, dict) else r[0]) or "Guest", "count": r["count"] if isinstance(r, dict) else r[1]}
        for r in loyalty_rows
    ]

    # 5. Top regular customers
    top_sql = f"""
        SELECT c.customer_id, c.name, c.phone, COALESCE(c.loyalty_tier, 'Standard') as loyalty_tier,
               COUNT(*) as visit_count, MAX(rl.timestamp) as last_seen
        FROM recognize_logs rl
        JOIN customers c ON rl.customer_id = c.customer_id
        {where_sql}
        WHERE c.customer_type NOT IN ('guest', 'temporary') OR c.customer_type IS NULL
        GROUP BY c.customer_id, c.name, c.phone, c.loyalty_tier
        ORDER BY visit_count DESC LIMIT 5
    """
    top_customers = [
        {
            "id":          r["customer_id"]  if isinstance(r, dict) else r[0],
            "name":        r["name"]         if isinstance(r, dict) else r[1],
            "phone":       r["phone"]        if isinstance(r, dict) else r[2],
            "loyalty_tier":r["loyalty_tier"] if isinstance(r, dict) else r[3],
            "visit_count": r["visit_count"]  if isinstance(r, dict) else r[4],
            "last_seen":   str(r["last_seen"] if isinstance(r, dict) else r[5]),
        }
        for r in conn.execute(top_sql, tuple(params)).fetchall()
    ]

    return {
        "summary": {
            "total_visits": total_visits,
            "vip_visits": vip_visits,
            "guest_visits": guest_visits,
            "unique_customers": unique_customers,
            "repeat_rate": repeat_rate,
            "peak_hour": peak_hour_item["hour"],
            "peak_count": peak_hour_item["count"],
        },
        "hourly_traffic": hourly_data,
        "daily_traffic": daily_data,
        "loyalty_distribution": loyalty_data,
        "top_customers": top_customers,
    }
