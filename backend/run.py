import uvicorn


def main():
    host = "0.0.0.0"
    port = 8000
    print(f"[INFO] Starting ASGI app on http://{host}:{port}")
    uvicorn.run("asgi:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()