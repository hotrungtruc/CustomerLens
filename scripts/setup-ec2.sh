#!/usr/bin/env bash
# ============================================================
# setup-ec2.sh  –  One-time EC2 setup script
# Run once manually after cloning the repo on a fresh EC2.
# ============================================================
set -e

echo "=== Face-AI EC2 Setup Script ==="

# 1. Create persistent data dirs (Docker volumes)
echo "[1/4] Creating volume directories..."
sudo mkdir -p /srv/faceai/models
sudo mkdir -p /srv/faceai/data/database
sudo mkdir -p /srv/faceai/data/encodings
sudo mkdir -p /srv/faceai/data/images
sudo chown -R ubuntu:ubuntu /srv/faceai
echo "  /srv/faceai/ created"

# 2. Pull latest code
echo "[2/4] Pulling latest code..."
cd /home/ubuntu/face-recognition-system
git pull origin main

# 3. Build and start the Docker container
echo "[3/4] Building Docker image and starting container..."
sudo docker compose down --timeout 30 2>/dev/null || true
sudo docker compose up --build -d

# 4. Verify
echo "[4/4] Verifying..."
sleep 20
sudo docker compose ps
echo ""
echo "=== Setup complete! ==="
echo "API should be accessible at http://localhost:8000"
echo "Run 'sudo docker compose logs -f backend' to watch logs."
