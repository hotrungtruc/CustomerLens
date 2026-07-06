import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.api.routes import router
from config import CORS_ORIGINS


from contextlib import asynccontextmanager
from app.db.connection import get_db_connection, ensure_schema

from app.api.routes import init_kafka_producer, close_kafka_producer

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://checkinface.me",
        "https://www.checkinface.me",
        "https://face-recognition-system-coral.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router)
