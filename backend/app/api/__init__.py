"""
API package — aggregates all domain routers into a single `router` object
so asgi.py only needs one import.

Import order matters for circular-import avoidance:
  messaging → auth → devices → customers → cameras
"""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.devices import router as devices_router
from app.api.customers import router as customers_router
from app.api.cameras import router as cameras_router

# Re-export Kafka lifecycle functions consumed by asgi.py
from app.messaging.kafka_client import init_kafka_producer, close_kafka_producer  # noqa: F401

router = APIRouter()
router.include_router(auth_router)
router.include_router(devices_router)
router.include_router(customers_router)
router.include_router(cameras_router)
