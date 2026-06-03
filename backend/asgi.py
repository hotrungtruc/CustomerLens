from concurrent.futures import ThreadPoolExecutor
import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.api.routes import camera_feed, init_models, router
from config import CORS_ORIGINS


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://checkinface.me",        
        "https://www.checkinface.me",   
        "https://face-recognition-system-coral.vercel.app", 
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

stream_executor: ThreadPoolExecutor | None = None
ai_executor: ThreadPoolExecutor | None = None

app.include_router(router)


@app.on_event("startup")
def startup_event():
    global stream_executor, ai_executor

    worker_count = max(2, min(4, (os.cpu_count() or 2)))
    ai_executor = ThreadPoolExecutor(max_workers=worker_count)
    stream_executor = ThreadPoolExecutor(max_workers=2)
    init_models(ai_executor=ai_executor)


@app.on_event("shutdown")
def shutdown_event():
    global stream_executor, ai_executor
    if stream_executor:
        stream_executor.shutdown(wait=False)
        stream_executor = None
    if ai_executor:
        ai_executor.shutdown(wait=False)
        ai_executor = None


async def _async_frame_generator():
    gen = camera_feed()
    loop = asyncio.get_running_loop()
    while True:
        try:
            frame = await loop.run_in_executor(stream_executor, next, gen)
        except StopIteration:
            break
        except Exception:
            break
        else:
            yield frame
            await asyncio.sleep(0.01)


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(_async_frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")



