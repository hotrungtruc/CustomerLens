#!/bin/bash
# setup_worker.sh — Cài đặt và khởi động AI Worker trên EC2 Worker nodes
# Chạy lần lượt trên: 54.253.192.210 (worker1) và 54.252.191.145 (worker2)
# Usage: bash setup_worker.sh <WORKER_PUBLIC_IP>
#
# Worker nodes chỉ chạy ai_worker service, kết nối về Master qua private IP

set -e

WORKER_IP="${1:?Usage: bash setup_worker.sh <WORKER_PUBLIC_IP>}"
MASTER_PRIVATE_IP="172.31.9.172"
SSH_KEY="$HOME/Downloads/WORKERS.pem"
REMOTE_USER="ubuntu"
APP_DIR="/home/ubuntu/CustomerLens"
REPO_URL="https://github.com/hotrungtruc/CustomerLens.git"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[WORKER]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=no $REMOTE_USER@$WORKER_IP"

log "Connecting to Worker: $WORKER_IP"
$SSH "echo 'SSH OK'"

# ── 1. Cài Docker ────────────────────────────────────────────
log "Installing Docker..."
$SSH "sudo apt-get update -qq && sudo apt-get install -y docker.io docker-compose-v2 git 2>&1 | tail -5"
$SSH "sudo usermod -aG docker ubuntu"

# ── 2. Clone repo ─────────────────────────────────────────────
log "Cloning repo..."
$SSH "
if [ ! -d $APP_DIR/.git ]; then
    git clone $REPO_URL $APP_DIR
else
    cd $APP_DIR && git pull origin main
fi
"

# ── 3. Upload Worker .env (trỏ Redis/Kafka về Master private IP)
log "Creating worker .env..."
$SSH "cat > $APP_DIR/backend/.env << 'EOF'
USE_SUPABASE=false
REDIS_URL=redis://$MASTER_PRIVATE_IP:6379/0
KAFKA_BOOTSTRAP_SERVERS=$MASTER_PRIVATE_IP:9092
RECOGNIZER_MODEL=edgeface
OMP_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2
MKL_NUM_THREADS=2
ONNX_INTRA_OP_NUM_THREADS=2
DEVICE_COOKIE_SECURE=true
EOF
echo '.env written'"

# ── 4. Upload AI models từ Master ────────────────────────────
log "Copying AI models from Master..."
SSH_MASTER="ssh -i $HOME/Downloads/MASTER.pem -o StrictHostKeyChecking=no ubuntu@15.134.121.250"
for model in edgeface_int8.onnx face_landmarker.task scrfd_500m_bnkps.onnx; do
    $SSH_MASTER "cat /home/ubuntu/CustomerLens/backend/models/$model" | \
    $SSH "cat > $APP_DIR/backend/models/$model"
    log "  - $model"
done

# ── 5. Build Docker image ─────────────────────────────────────
log "Building Docker image..."
$SSH "cd $APP_DIR && sudo docker compose -f docker-compose.worker.yml build --no-cache ai_worker 2>&1 | tail -10"

# ── 6. Start Worker ───────────────────────────────────────────
log "Starting ai_worker..."
$SSH "cd $APP_DIR && sudo docker compose -f docker-compose.worker.yml up -d"
$SSH "sudo docker ps"

log "[DONE] Worker $WORKER_IP setup complete!"
