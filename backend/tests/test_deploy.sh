#!/bin/bash
MASTER_IP="15.134.121.250"
EC2_USER="ubuntu"
ssh -i C:/Users/hotru/Downloads/master.pem -o StrictHostKeyChecking=no "$EC2_USER@$MASTER_IP" << 'ENDSSH'
set -e
echo "--- Pulling latest code on Master ---"
cd /home/ubuntu/face-recognition-system
git fetch origin main
git reset --hard origin/main

echo "--- Rebuilding and restarting container ---"
sudo docker compose down --timeout 30
sudo docker compose up --build -d
sudo docker image prune -f
ENDSSH
