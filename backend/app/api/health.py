"""
Health check & metrics endpoints.
Provides production observability for orchestration (Kubernetes, Docker),
monitoring systems (Prometheus, Datadog), and uptime monitors.
"""

import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from app.db.connection import get_db_connection
from config import REDIS_URL, USE_SUPABASE

START_TIME = time.time()
router = APIRouter(tags=["monitoring"])


@router.get("/api/health")
def api_health(response: Response):
    """
    Comprehensive system health check.
    Validates Database connectivity and Redis availability.
    """
    checks = {}
    overall_healthy = True

    # 1. Database Check
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            checks["database"] = {
                "status": "up",
                "type": "supabase_postgresql" if USE_SUPABASE else "sqlite_wal",
            }
        finally:
            conn.close()
    except Exception as exc:
        checks["database"] = {"status": "down", "error": str(exc)}
        overall_healthy = False

    # 2. Redis Check
    try:
        import redis
        r = redis.from_url(REDIS_URL, socket_timeout=1.0)
        r.ping()
        checks["redis"] = {"status": "up"}
    except Exception as exc:
        checks["redis"] = {"status": "down", "error": str(exc)}
        # Redis being down is degraded rather than critical failure
        if checks.get("database", {}).get("status") != "up":
            overall_healthy = False

    uptime_seconds = int(time.time() - START_TIME)
    health_payload = {
        "status": "healthy" if overall_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_seconds,
        "environment": "production" if os.getenv("ENVIRONMENT") == "production" else "development",
        "checks": checks,
    }

    if not overall_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return health_payload


@router.get("/api/metrics")
def api_metrics():
    """
    Metrics endpoint for system observability and monitoring.
    """
    uptime_seconds = int(time.time() - START_TIME)
    
    # Active camera count from in-memory state
    active_cameras = 0
    try:
        from app.api.devices import CAMERA_STATES, CAMERA_STATES_LOCK
        with CAMERA_STATES_LOCK:
            active_cameras = len(CAMERA_STATES)
    except Exception:
        pass

    return {
        "system": {
            "uptime_seconds": uptime_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "devices": {
            "active_cameras": active_cameras,
        },
        "database": {
            "type": "supabase_postgresql" if USE_SUPABASE else "sqlite",
        },
    }
