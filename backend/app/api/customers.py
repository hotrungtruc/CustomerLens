"""
Customer-related routes:
- GET  /api/customers              list all customers
- GET  /api/customer_info          customer info for current detection
- GET  /api/customers_overview     all detected customers overview
- GET  /api/customer_profile_by_id/{customer_id}
- PUT  /api/customer_profile       create / update profile
- POST /api/check_in               check-in current detection
- POST /api/check_in/{customer_id} check-in by id
- POST /api/promote_guest          promote guest → registered customer
- GET  /api/logs                   recognition logs
- GET  /api/logs/export            export logs as CSV
- GET  /api/reports                analytical reports
- POST /api/admin/purge_guests     GDPR purge
"""

import csv
import io
import json
import math
import time
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response

from app.api.auth import get_user_from_token, require_admin
from app.db.connection import (
    create_or_update_customer_profile,
    get_customer_info,
    get_db_connection,
    update_attendance,
    bulk_insert_recognize_logs,
    get_recognize_logs,
    get_reports_data,
)
from app.messaging.kafka_client import get_redis
from config import CHECKIN_COOLDOWN_SECONDS

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helper shared with devices.py
# ---------------------------------------------------------------------------

def _apply_profile_to_payload(payload: dict, info: dict):
    def safe_iso(val):
        return val.isoformat() if isinstance(val, datetime) else val

    from app.core.customer_code import compute_segment_code
    code, label, desc = compute_segment_code(info)

    payload.update(
        {
            "id": info["customer_id"],
            "name": info["name"] or "Khach moi",
            "email": info.get("email"),
            "registered_at": safe_iso(info.get("registered_at")),
            "tenure": info.get("tenure", 0),
            "loyalty_tier": info.get("loyalty_tier", "Standard"),
            "total_visits": info.get("total_visits", 0),
            "last_visit": safe_iso(info.get("last_visit")),
            "total_spending": info.get("total_spending", 0),
            "service_category": info.get("service_category", "General"),
            "service_start_year": info.get("service_start_year", 0),
            "customer_tenure_years": info.get("customer_tenure_years", 0),
            "customer_type": info.get("customer_type", "guest"),
            "customer_status": info.get("status", "active"),
            "segment_code": code,
            "segment_label": label,
            "segment_desc": desc,
            "has_face_embedding": info.get("has_face_embedding"),
            "face_embedding_dim": info.get("face_embedding_dim"),
            "face_embedding_model": info.get("face_embedding_model"),
            "phone": info.get("phone"),
            "note": info.get("note"),
        }
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/api/customers")
def api_get_all_customers(authorization: str | None = Header(None)):
    require_admin(authorization)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT customer_id as id, name, phone, note,
                   total_visits as total_attendance,
                   last_visit as last_attendance_time
            FROM customers
            """
        )
        rows = cursor.fetchall()
        customers = [dict(row) for row in rows]
        return {"status": "success", "customers": customers}
    finally:
        conn.close()


@router.get("/api/customer_info")
def api_customer_info(camera_id: str | None = None):
    # Import here to avoid circular dependency with devices.py
    from app.api.devices import get_camera_state

    state = get_camera_state(camera_id)
    detected_customer_id = None
    for c in state.latest_customers_payload:
        if c.get("id"):
            detected_customer_id = c["id"]
            break

    if not detected_customer_id:
        return {"status": "no_detection"}

    conn = get_db_connection()
    try:
        customer_info = get_customer_info(conn, detected_customer_id)
        if not customer_info:
            return {"status": "not_found"}

        return {
            "status": "success",
            "id": customer_info["customer_id"],
            "name": customer_info["name"],
            "phone": customer_info.get("phone"),
            "email": customer_info.get("email"),
            "registered_at": customer_info.get("registered_at"),
            "tenure": customer_info.get("tenure"),
            "loyalty_tier": customer_info.get("loyalty_tier"),
            "total_visits": customer_info.get("total_visits", 0),
            "last_visit": customer_info.get("last_visit"),
            "total_spending": customer_info.get("total_spending", 0),
            "service_category": customer_info["service_category"],
            "service_start_year": customer_info["service_start_year"],
            "customer_tenure_years": customer_info["customer_tenure_years"],
            "customer_type": customer_info["customer_type"],
            "customer_status": customer_info["status"],
            "has_face_embedding": customer_info.get("has_face_embedding"),
            "face_embedding_dim": customer_info.get("face_embedding_dim"),
            "face_embedding_model": customer_info.get("face_embedding_model"),
            "major": customer_info["major"],
            "year": customer_info["year"],
            "starting_year": customer_info["starting_year"],
            "total_attendance": customer_info["total_attendance"],
            "visit_count": customer_info["total_attendance"],
            "note": customer_info.get("note"),
            "standing": customer_info["standing"],
            "last_attendance_time": customer_info["last_attendance_time"],
            "image": None,
        }
    finally:
        conn.close()


@router.get("/api/customers_overview")
def api_customers_overview(camera_id: str | None = None):
    from app.api.devices import get_camera_state
    from config import FRAME_WIDTH, FRAME_HEIGHT

    state = get_camera_state(camera_id)
    customers = state.latest_customers_payload

    if not customers:
        return {
            "status": "no_detection",
            "customers": [],
            "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
        }

    status = "success" if any(item.get("detected") for item in customers) else "no_detection"
    return {
        "status": status,
        "customers": customers,
        "frame_size": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
    }


@router.get("/api/customer_profile_by_id/{customer_id}")
def api_get_customer_by_id(
    customer_id: str, authorization: str | None = Header(None)
):
    require_admin(authorization)
    conn = get_db_connection()
    try:
        customer_info = get_customer_info(conn, customer_id)
        if not customer_info:
            return {
                "status": "not_found",
                "message": f"Customer '{customer_id}' not found",
            }
        return {
            "status": "success",
            "customer": {
                "id": customer_info["customer_id"],
                "name": customer_info["name"],
                "phone": customer_info.get("phone"),
                "total_attendance": customer_info["total_attendance"],
                "last_attendance_time": customer_info["last_attendance_time"],
                "note": customer_info.get("note"),
            },
        }
    finally:
        conn.close()


@router.put("/api/customer_profile")
async def api_customer_profile(
    request: Request, authorization: str | None = Header(None)
):
    from app.api.devices import CAMERA_STATES, CAMERA_STATES_LOCK

    require_admin(authorization)
    payload = await request.json()
    selected_id = (payload.get("id") or "").strip()
    source_id = (payload.get("source_id") or selected_id or "").strip()
    name = payload.get("name")
    phone = payload.get("phone")
    email = payload.get("email")
    note = payload.get("note")
    service_category = payload.get("service_category")
    service_start_year = payload.get("service_start_year")
    customer_tenure_years = payload.get("customer_tenure_years")
    loyalty_tier = payload.get("loyalty_tier") or payload.get("rank")

    conn = get_db_connection()
    final_id = selected_id

    try:
        writable_id = selected_id
        created = False
        if (
            writable_id.startswith("T")
            or writable_id.startswith("GUEST_")
            or writable_id.startswith("test_")
            or writable_id.startswith("LN")
        ):
            writable_id = None

        try:
            final_id, created = create_or_update_customer_profile(
                conn,
                customer_id=writable_id,
                source_id=source_id,
                name=name,
                phone=phone,
                email=email,
                note=note,
                service_category=service_category,
                service_start_year=service_start_year,
                customer_tenure_years=customer_tenure_years,
                loyalty_tier=loyalty_tier,
            )
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

        if (source_id.startswith("GUEST_") or source_id.startswith("test_") or source_id.startswith("LN")) and final_id != source_id:
            camera_id = "default"
            parts = source_id.split("_")
            if len(parts) >= 3:
                prefix = "_".join(parts[:-2])
                if prefix.startswith("GUEST_"):
                    camera_id = prefix[len("GUEST_"):]

            r = await get_redis()
            await r.publish(
                f"camera_control:{camera_id}",
                json.dumps({"action": "promote_guest", "guest_id": source_id, "new_id": final_id}),
            )
            with CAMERA_STATES_LOCK:
                for cid in CAMERA_STATES.keys():
                    if cid != camera_id:
                        await r.publish(
                            f"camera_control:{cid}",
                            json.dumps({"action": "promote_guest", "guest_id": source_id, "new_id": final_id}),
                        )
                    await r.publish(
                        f"camera_control:{cid}",
                        json.dumps({"action": "reload_embeddings"}),
                    )

        customer_info = get_customer_info(conn, final_id)
        if not customer_info:
            return {"success": False, "message": "Customer not found after save"}

        return {
            "success": True,
            "created": created,
            "customer": {
                "id": customer_info["customer_id"],
                "customer_id": customer_info["customer_id"],
                "name": customer_info["name"],
                "phone": customer_info.get("phone"),
                "email": customer_info.get("email"),
                "registered_at": customer_info.get("registered_at"),
                "tenure": customer_info.get("tenure"),
                "loyalty_tier": customer_info.get("loyalty_tier"),
                "total_visits": customer_info.get("total_visits", 0),
                "last_visit": customer_info.get("last_visit"),
                "total_spending": customer_info.get("total_spending", 0),
                "note": customer_info.get("note"),
                "service_category": customer_info.get("service_category"),
                "service_start_year": customer_info.get("service_start_year"),
                "customer_tenure_years": customer_info.get("customer_tenure_years"),
                "customer_type": customer_info.get("customer_type"),
                "customer_status": customer_info.get("status"),
                "has_face_embedding": customer_info.get("has_face_embedding"),
                "face_embedding_dim": customer_info.get("face_embedding_dim"),
                "face_embedding_model": customer_info.get("face_embedding_model"),
                "visit_count": customer_info.get("total_attendance", 0),
                "last_attendance_time": customer_info.get("last_attendance_time"),
            },
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            r = await get_redis()
            with CAMERA_STATES_LOCK:
                for cid in CAMERA_STATES.keys():
                    await r.publish(
                        f"camera_control:{cid}",
                        json.dumps({"action": "invalidate_cache", "customer_id": final_id}),
                    )
        except Exception:
            pass


@router.post("/api/check_in")
def api_check_in(camera_id: str | None = None):
    from app.api.devices import get_camera_state

    state = get_camera_state(camera_id)
    detected_customer_id = None
    for c in state.latest_customers_payload:
        if c.get("id"):
            detected_customer_id = c["id"]
            break

    if not detected_customer_id:
        return {"success": False, "message": "No face detected"}

    conn = get_db_connection()
    try:
        customer_info = get_customer_info(conn, detected_customer_id)
        if not customer_info:
            return {"success": False, "message": "Customer not found"}

        try:
            last_time = datetime.strptime(
                customer_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
            )
        except (TypeError, ValueError):
            last_time = datetime.min

        seconds_elapsed = (datetime.now() - last_time).total_seconds()
        if seconds_elapsed > CHECKIN_COOLDOWN_SECONDS:
            update_attendance(
                conn,
                detected_customer_id,
                customer_info["total_attendance"] + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            return {"success": True, "message": "Check-in successful"}

        remaining = int(CHECKIN_COOLDOWN_SECONDS - seconds_elapsed)
        return {"success": False, "message": f"Please wait {remaining}s"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}
    finally:
        conn.close()


@router.post("/api/check_in/{customer_id}")
def api_check_in_by_id(customer_id: str):
    conn = get_db_connection()
    try:
        customer_info = get_customer_info(conn, customer_id)
        if not customer_info:
            return {"success": False, "message": "Customer not found"}

        try:
            last_time = datetime.strptime(
                customer_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
            )
        except (TypeError, ValueError):
            last_time = datetime.min

        seconds_elapsed = (datetime.now() - last_time).total_seconds()
        if seconds_elapsed > CHECKIN_COOLDOWN_SECONDS:
            update_attendance(
                conn,
                customer_id,
                customer_info["total_attendance"] + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            return {"success": True, "message": "Check-in successful"}

        remaining = int(CHECKIN_COOLDOWN_SECONDS - seconds_elapsed)
        return {"success": False, "message": f"Please wait {remaining}s"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}
    finally:
        conn.close()


@router.post("/api/promote_guest")
async def api_promote_guest(
    request: Request, authorization: str | None = Header(None)
):
    from app.api.devices import CAMERA_STATES, CAMERA_STATES_LOCK

    require_admin(authorization)
    payload = await request.json()
    guest_id = payload.get("guest_id")
    new_id = payload.get("new_id")
    if not guest_id or not new_id:
        return {"success": False, "message": "guest_id and new_id required"}

    camera_id = "default"
    if guest_id.startswith("GUEST_"):
        parts = guest_id.split("_")
        if len(parts) >= 3:
            prefix = "_".join(parts[:-2])
            if prefix.startswith("GUEST_"):
                camera_id = prefix[len("GUEST_"):]

    r = await get_redis()
    await r.publish(
        f"camera_control:{camera_id}",
        json.dumps({"action": "promote_guest", "guest_id": guest_id, "new_id": new_id}),
    )
    with CAMERA_STATES_LOCK:
        for cid in CAMERA_STATES.keys():
            if cid != camera_id:
                await r.publish(
                    f"camera_control:{cid}",
                    json.dumps({"action": "promote_guest", "guest_id": guest_id, "new_id": new_id}),
                )
            await r.publish(
                f"camera_control:{cid}",
                json.dumps({"action": "reload_embeddings"}),
            )
    return {"success": True}


@router.get("/api/logs")
def api_get_recognize_logs(
    start_date: str = None,
    end_date: str = None,
    camera_id: str = None,
    customer_type: str = None,
    search: str = None,
    page: int = 1,
    limit: int = 50,
):
    """Get recognition event logs with date range, camera, type, search and pagination."""
    conn = get_db_connection()
    try:
        offset = max(0, (page - 1) * limit)
        result = get_recognize_logs(
            conn,
            start_date=start_date,
            end_date=end_date,
            camera_id=camera_id,
            customer_type=customer_type,
            search=search,
            limit=limit,
            offset=offset,
        )
        return {
            "success": True,
            "logs": result["logs"],
            "total_count": result["total_count"],
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(result["total_count"] / limit) if limit > 0 else 1,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error fetching logs: {str(e)}",
            "logs": [],
            "total_count": 0,
        }
    finally:
        conn.close()


@router.get("/api/logs/export")
def api_export_recognize_logs_csv(
    start_date: str = None,
    end_date: str = None,
    camera_id: str = None,
    customer_type: str = None,
    search: str = None,
):
    """Export filtered recognition logs as CSV (UTF-8 BOM for Excel compatibility)."""
    conn = get_db_connection()
    try:
        result = get_recognize_logs(
            conn,
            start_date=start_date,
            end_date=end_date,
            camera_id=camera_id,
            customer_type=customer_type,
            search=search,
            limit=10000,
            offset=0,
        )
        logs = result["logs"]

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(
            [
                "Mã Log", "Thời Gian", "Camera ID", "Tên Camera",
                "Mã Khách hàng", "Tên Khách hàng", "Số Điện thoại",
                "Loại Khách", "Hạng Thành viên", "Track ID",
            ]
        )
        for log in logs:
            writer.writerow(
                [
                    log.get("id") or "",
                    log.get("timestamp") or "",
                    log.get("camera_id") or "",
                    log.get("camera_name") or "",
                    log.get("customer_id") or "",
                    log.get("customer_name") or "",
                    log.get("customer_phone") or "",
                    log.get("customer_type") or "guest",
                    log.get("loyalty_tier") or "Standard",
                    log.get("track_id") or "",
                ]
            )

        csv_data = output.getvalue()
        filename = f"nhat_ky_nhan_dien_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return Response(content=f"Error exporting CSV: {str(e)}", status_code=500)
    finally:
        conn.close()


@router.get("/api/reports")
def api_get_reports_data(
    start_date: str = None,
    end_date: str = None,
    camera_id: str = None,
):
    """Analytical reports: hourly traffic, daily counts, loyalty distribution, top customers."""
    conn = get_db_connection()
    try:
        data = get_reports_data(conn, start_date=start_date, end_date=end_date, camera_id=camera_id)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "message": f"Error loading reports data: {str(e)}"}
    finally:
        conn.close()


@router.post("/api/admin/purge_guests")
def api_purge_guests(
    retention_days: int | None = None,
    authorization: str | None = Header(None),
):
    """GDPR Article 17 (Right to be Forgotten) — purge guest records."""
    from app.core.biometric_security import purge_expired_guests

    require_admin(authorization)
    conn = get_db_connection()
    try:
        days = retention_days if retention_days is not None else 30
        result = purge_expired_guests(conn, retention_days=days)
        return {"status": "success", "data": result}
    finally:
        conn.close()
