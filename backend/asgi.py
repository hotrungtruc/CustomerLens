from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.api import routes as flask_routes
from app.db.connection import ensure_schema, get_customer_info, get_db_connection


app = FastAPI()

# Executor for CPU-bound AI work and camera pipeline
executor: ThreadPoolExecutor | None = None


@app.on_event("startup")
def startup_event():
    global executor
    # initialize models and track manager (same as Flask init_models)
    flask_routes.init_models()
    # create a dedicated thread pool for CPU-bound tasks
    executor = ThreadPoolExecutor(max_workers=4)


@app.on_event("shutdown")
def shutdown_event():
    global executor
    if executor:
        executor.shutdown(wait=False)
        executor = None


@app.get("/")
def index():
    return {"status": "ok", "message": "ASGI backend running"}


async def _async_frame_generator():
    """Run the synchronous camera generator inside the threadpool so the event loop stays responsive."""
    gen = flask_routes.camera_feed()
    loop = asyncio.get_event_loop()
    while True:
        try:
            # offload the blocking `next(gen)` call
            frame = await loop.run_in_executor(executor, next, gen)
        except StopIteration:
            break
        except Exception:
            # if the generator blocks or errors, stop the stream
            break
        else:
            yield frame


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(_async_frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/customer_info")
def api_customer_info():
    current_customer_id = flask_routes.current_customer_id
    if not current_customer_id:
        return JSONResponse({"status": "no_detection"})

    conn = get_db_connection()
    ensure_schema(conn)
    try:
        customer_info = get_customer_info(conn, current_customer_id)
        if not customer_info:
            return JSONResponse({"status": "not_found"})

        img_base64 = flask_routes.__load_customer_image_base64(current_customer_id)
        return JSONResponse(
            {
                "status": "success",
                "id": customer_info["id"],
                "name": customer_info["name"],
                "major": customer_info["major"],
                "year": customer_info["year"],
                "starting_year": customer_info["starting_year"],
                "total_attendance": customer_info["total_attendance"],
                "standing": customer_info["standing"],
                "last_attendance_time": customer_info["last_attendance_time"],
                "image": img_base64,
            }
        )
    finally:
        conn.close()


@app.post("/api/check_in")
def api_check_in():
    current_customer_id = flask_routes.current_customer_id
    if not current_customer_id:
        return JSONResponse({"success": False, "message": "No face detected"})

    conn = get_db_connection()
    ensure_schema(conn)
    try:
        customer_info = get_customer_info(conn, current_customer_id)
        if not customer_info:
            return JSONResponse({"success": False, "message": "Customer not found"})

        from datetime import datetime

        try:
            last_time = datetime.strptime(
                customer_info["last_attendance_time"], "%Y-%m-%d %H:%M:%S"
            )
        except (TypeError, ValueError):
            from datetime import datetime as _dt

            last_time = _dt.min

        seconds_elapsed = (datetime.now() - last_time).total_seconds()
        from config import CHECKIN_COOLDOWN_SECONDS

        if seconds_elapsed > CHECKIN_COOLDOWN_SECONDS:
            from app.db.connection import update_attendance

            update_attendance(
                conn,
                current_customer_id,
                customer_info["total_attendance"] + 1,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            return JSONResponse({"success": True, "message": "Check-in successful"})

        remaining = int(CHECKIN_COOLDOWN_SECONDS - seconds_elapsed)
        return JSONResponse({"success": False, "message": f"Please wait {remaining}s"})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error: {str(e)}"})
    finally:
        conn.close()

