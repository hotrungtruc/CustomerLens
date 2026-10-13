#!/bin/bash
MASTER_IP="15.134.121.250"
EC2_USER="ubuntu"
ssh -i C:/Users/hotru/Downloads/master.pem -o StrictHostKeyChecking=no "$EC2_USER@$MASTER_IP" << 'ENDSSH'
set -e
if [ -d "/home/ubuntu/CustomerLens" ]; then
  APP_DIR="/home/ubuntu/CustomerLens"
elif [ -d "/home/ubuntu/face-recognition-system" ]; then
  APP_DIR="/home/ubuntu/face-recognition-system"
else
  echo "Error: Application directory not found!" && exit 1
fi
cd "$APP_DIR"
git fetch origin main
git reset --hard origin/main

echo "--- Rebuilding and restarting container ---"
sudo docker compose down --timeout 30
sudo docker compose up --build -d
sudo docker image prune -f
ENDSSH
