FROM python:3.12-slim

WORKDIR /app

# System libs required by OpenCV & MediaPipe at runtime + curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libgles2 \
    libegl1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy application code (models/ and data/ are mounted as volumes)
COPY asgi.py run.py config.py db_config.py ./
COPY app/ ./app/

# Create volume mount points so Docker knows to expect external data here
VOLUME ["/app/models", "/app/data"]

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=2
ENV OPENBLAS_NUM_THREADS=2
ENV MKL_NUM_THREADS=2

CMD ["python", "run.py"]
