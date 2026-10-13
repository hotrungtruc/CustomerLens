#!/bin/bash
# ============================================================
# deploy_backend.sh — Triển khai CustomerLens Backend lên EC2
# Chạy từ máy LOCAL (Windows/Linux/Mac) với SSH key MASTER.pem
# Usage: bash deploy_backend.sh
# ============================================================

set -euo pipefail

MASTER_IP="15.134.121.250"
SSH_KEY="$HOME/Downloads/MASTER.pem"
REMOTE_USER="ubuntu"
APP_DIR="/home/ubuntu/CustomerLens"
REPO_URL="https://github.com/hotrungtruc/CustomerLens.git"  # chỉnh nếu khác

# Màu sắc
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=no $REMOTE_USER@$MASTER_IP"

# ── 1. Ping kiểm tra kết nối ─────────────────────────────────
log "Kiểm tra kết nối SSH tới Master ($MASTER_IP)..."
$SSH "echo 'SSH OK'" || err "Không kết nối được Master!"

# ── 2. Cài đặt Docker & Docker Compose nếu chưa có ──────────
log "Đảm bảo Docker và Docker Compose đã cài..."
$SSH "bash -s" <<'REMOTE'
if ! command -v docker &>/dev/null; then
    echo "Cài Docker..."
    curl -fsSL https://get.docker.com | sudo bash
    sudo usermod -aG docker ubuntu
    newgrp docker
fi
if ! docker compose version &>/dev/null; then
    echo "Cài Docker Compose plugin..."
    sudo apt-get install -y docker-compose-plugin
fi
echo "Docker: $(docker --version)"
echo "Compose: $(docker compose version)"
REMOTE

# ── 3. Clone hoặc Pull code ──────────────────────────────────
log "Lấy code mới nhất từ repo..."
$SSH "bash -s" <<REMOTE
if [ ! -d "$APP_DIR/.git" ]; then
    echo "Clone repo lần đầu..."
    git clone $REPO_URL $APP_DIR
else
    echo "Pull code mới nhất..."
    cd $APP_DIR && git pull origin main
fi
REMOTE

# ── 4. Upload .env production ────────────────────────────────
log "Upload file .env production..."
scp -i $SSH_KEY -o StrictHostKeyChecking=no \
    "$(dirname "$0")/backend/.env.production" \
    "$REMOTE_USER@$MASTER_IP:$APP_DIR/backend/.env"

# ── 5. Upload Cloudflare SSL certs (nếu chưa có) ────────────
log "Cài Cloudflare Origin Certificate..."
$SSH "bash -s" <<'REMOTE'
if [ ! -f /etc/ssl/certs/cloudflare_origin.pem ]; then
    echo "Cert chưa có trong /etc/ssl/certs — copy từ /tmp..."
    sudo cp /tmp/cloudflare_origin.pem /etc/ssl/certs/cloudflare_origin.pem
    sudo chmod 644 /etc/ssl/certs/cloudflare_origin.pem
else
    echo "Cert đã tồn tại."
fi

if [ ! -f /etc/ssl/private/cloudflare_origin.key ]; then
    echo "Key chưa có — copy từ /tmp..."
    sudo cp /tmp/cloudflare_origin.key /etc/ssl/private/cloudflare_origin.key
    sudo chmod 600 /etc/ssl/private/cloudflare_origin.key
else
    echo "Key đã tồn tại."
fi
REMOTE

# ── 6. Cài Nginx và upload config ───────────────────────────
log "Cấu hình Nginx..."
$SSH "sudo apt-get install -y nginx 2>/dev/null | tail -3"
scp -i $SSH_KEY -o StrictHostKeyChecking=no \
    "$(dirname "$0")/nginx_api.conf" \
    "$REMOTE_USER@$MASTER_IP:/tmp/nginx_api.conf"
$SSH "sudo cp /tmp/nginx_api.conf /etc/nginx/sites-available/api.checkinface.me \
      && sudo ln -sf /etc/nginx/sites-available/api.checkinface.me /etc/nginx/sites-enabled/ \
      && sudo rm -f /etc/nginx/sites-enabled/default \
      && sudo nginx -t \
      && sudo systemctl reload nginx"

# ── 7. Build & khởi động Docker Compose ─────────────────────
log "Build và khởi động backend..."
$SSH "bash -s" <<REMOTE
cd $APP_DIR
docker compose pull redis redpanda 2>/dev/null || true
docker compose build --no-cache backend
docker compose up -d
docker compose ps
REMOTE

# ── 8. Health check ──────────────────────────────────────────
log "Kiểm tra health endpoint..."
sleep 10
HTTP_CODE=$($SSH "curl -sk -o /dev/null -w '%{http_code}' https://api.checkinface.me/")
if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "307" || "$HTTP_CODE" == "404" ]]; then
    log "[OK] Backend is running! HTTP $HTTP_CODE"
else
    warn "[WARN] HTTP $HTTP_CODE - check logs: docker compose logs backend"
fi

log "[DONE] Deployment complete!"
