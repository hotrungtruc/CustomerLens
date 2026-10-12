@echo off
echo ========================================================
echo   CustomerLens - Deploy Environment Variables to EC2
echo ========================================================
echo.

set MASTER_IP=15.134.121.250
set WORKER1_IP=54.253.192.210
set WORKER2_IP=54.252.191.145

set MASTER_KEY="C:\Users\hotru\Downloads\MASTER.pem"
set WORKERS_KEY="C:\Users\hotru\Downloads\WORKERS.pem"

echo [1/3] Copying .env.production to Master (%MASTER_IP%)...
scp -i %MASTER_KEY% -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL "backend\.env.production" ubuntu@%MASTER_IP%:~/CustomerLens/backend/.env

echo.
echo [2/3] Copying .env.production to Worker 1 (%WORKER1_IP%)...
scp -i %WORKERS_KEY% -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL "backend\.env.production" ubuntu@%WORKER1_IP%:~/CustomerLens/backend/.env

echo.
echo [3/3] Copying .env.production to Worker 2 (%WORKER2_IP%)...
scp -i %WORKERS_KEY% -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL "backend\.env.production" ubuntu@%WORKER2_IP%:~/CustomerLens/backend/.env

echo.
echo ========================================================
echo   Hoan thanh copy .env!
echo   SSH Manual Commands:
echo   - Master:   ssh -i %MASTER_KEY% ubuntu@%MASTER_IP%
echo   - Worker 1: ssh -i %WORKERS_KEY% ubuntu@%WORKER1_IP%
echo   - Worker 2: ssh -i %WORKERS_KEY% ubuntu@%WORKER2_IP%
echo ========================================================
echo.
pause
