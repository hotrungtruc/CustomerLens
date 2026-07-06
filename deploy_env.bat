@echo off
echo Dang copy file backend/.env len cac server EC2...
echo.
echo ========================================================
echo LUU Y: TRUOC KHI CHAY SCRIPT NAY, HAY DAM BAO FILE backend/.env
echo CUA BAN DA CAU HINH CAC BIEN SAU TRO DEN MASTER IP (15.134.121.250):
echo REDIS_URL=redis://15.134.121.250:6379/0
echo KAFKA_BOOTSTRAP_SERVERS=15.134.121.250:9092
echo ========================================================
echo.

echo [1/3] Copying to Master (15.134.121.250)...
scp -i "C:\Users\hotru\Downloads\master.pem" -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL "backend\.env" ubuntu@15.134.121.250:~/face-recognition-system/backend/.env

echo.
echo [2/3] Copying to Worker 1 (3.26.147.158)...
scp -i "C:\Users\hotru\Downloads\workers_2.pem" -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL "backend\.env" ubuntu@3.26.147.158:~/face-recognition-system/backend/.env

echo.
echo [3/3] Copying to Worker 2 (3.107.239.168)...
scp -i "C:\Users\hotru\Downloads\workers_2.pem" -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL "backend\.env" ubuntu@3.107.239.168:~/face-recognition-system/backend/.env

echo.
echo Hoan thanh qua trinh copy. Kiem tra cac thong bao loi (neu co) o tren.
echo.
echo Neu can SSH thu cong:
echo - Master: ssh -i "C:\Users\hotru\Downloads\master.pem" ubuntu@15.134.121.250
echo - Worker 1: ssh -i "C:\Users\hotru\Downloads\workers_2.pem" ubuntu@3.26.147.158
echo - Worker 2: ssh -i "C:\Users\hotru\Downloads\workers_2.pem" ubuntu@3.107.239.168
echo.
pause
