import uvicorn


def main():
    host = "127.0.0.1"
    port = 8000
    print(f"[INFO] Starting ASGI app on http://{host}:{port}")
    uvicorn.run("asgi:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
