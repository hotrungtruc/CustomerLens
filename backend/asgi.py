import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import router, init_kafka_producer, close_kafka_producer
from app.api.auth import limiter
from app.api.edge_routes import router as edge_router
from app.db.connection import get_db_connection, ensure_schema
from config import ALLOWED_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database schema on startup
    conn = get_db_connection()
    try:
        ensure_schema(conn)
    finally:
        conn.close()

    await init_kafka_producer()
    yield
    await close_kafka_producer()


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(edge_router, prefix="/api/v1/edge", tags=["edge"])
