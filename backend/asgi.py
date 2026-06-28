import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.api.routes import router
from config import CORS_ORIGINS


app = FastAPI()

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
