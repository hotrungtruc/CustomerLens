# ---- Stage 1: Builder ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps for packages that compile C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-prod.txt

# ---- Stage 2: Runtime ----
FROM python:3.12-slim

# System libs required by OpenCV & MediaPipe at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libgles2 \
    libegl1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code (models/ and data/ are mounted as volumes)
COPY asgi.py run.py config.py db_config.py ./
COPY app/ ./app/

# Create volume mount points so Docker knows to expect external data here
VOLUME ["/app/models", "/app/data"]

EXPOSE 8000

CMD ["python", "run.py"]
