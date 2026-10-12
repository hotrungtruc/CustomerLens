#!/usr/bin/env bash
# ============================================================
# setup-ec2.sh  –  CustomerLens One-time / Update EC2 setup script
# Supports both Master Node and Worker Nodes.
# ============================================================
set -e

ROLE="${1:-master}"  # 'master' or 'worker'

echo "============================================================"
echo "  CustomerLens EC2 Deployment Setup (Role: $ROLE)"
echo "============================================================"

# 1. Install Docker & Docker Compose if missing
if ! command -v docker &> /dev/null; then
    echo "[1/5] Installing Docker & Docker Compose plugin..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker ubuntu
    echo "Docker installed successfully."
else
    echo "[1/5] Docker is already installed."
fi

# 2. Clone or Update CustomerLens repository
REPO_DIR="/home/ubuntu/CustomerLens"
REPO_URL="https://github.com/hotrungtruc/CustomerLens.git"

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "[2/5] Cloning CustomerLens repository..."
    cd /home/ubuntu
    git clone "$REPO_URL" CustomerLens
    cd "$REPO_DIR"
else
    echo "[2/5] Updating CustomerLens repository..."
    cd "$REPO_DIR"
    git fetch origin main
    git reset --hard origin/main
fi

# 3. Create persistent directories
echo "[3/5] Setting up data & model directories..."
mkdir -p "$REPO_DIR/backend/models"
mkdir -p "$REPO_DIR/backend/data/database"
mkdir -p "$REPO_DIR/backend/data/images"
mkdir -p "$REPO_DIR/backend/data/encodings"
mkdir -p "$REPO_DIR/backend/data/keys"

# 4. Check for .env file
if [ ! -f "$REPO_DIR/backend/.env" ]; then
    echo "[!] Warning: backend/.env is missing. Creating template..."
    if [ -f "$REPO_DIR/backend/.env.production" ]; then
        cp "$REPO_DIR/backend/.env.production" "$REPO_DIR/backend/.env"
    else
        cat << 'EOF' > "$REPO_DIR/backend/.env"
USE_SUPABASE=false
ADMIN_PASSWORD=admin123
MOD_PASSWORD=moderator123
REDIS_URL=redis://172.31.9.172:6379/0
KAFKA_BOOTSTRAP_SERVERS=172.31.9.172:9092
DEVICE_COOKIE_SECURE=false
WS_ALLOWED_ORIGINS=http://15.134.121.250,http://15.134.121.250:8000,http://15.134.121.250:3000,http://localhost:3000
EOF
    fi
fi

# 5. Build and launch services
echo "[4/5] Building & Launching containers..."
if [ "$ROLE" = "worker" ]; then
    echo "Starting AI Worker service..."
    sudo docker compose -f docker-compose.worker.yml down --timeout 30 2>/dev/null || true
    sudo docker compose -f docker-compose.worker.yml up --build -d
    echo "[5/5] Worker container status:"
    sleep 5
    sudo docker compose -f docker-compose.worker.yml ps
else
    echo "Starting Master stack (Backend, Redis, Redpanda, AI Worker)..."
    sudo docker compose down --timeout 30 2>/dev/null || true
    sudo docker compose up --build -d
    echo "[5/5] Master stack status:"
    sleep 10
    sudo docker compose ps
fi

echo ""
echo "============================================================"
echo "  Deployment Complete! Role: $ROLE"
echo "============================================================"
