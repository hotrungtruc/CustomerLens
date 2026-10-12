# ============================================================
# deploy-ec2.ps1 – Automated CustomerLens EC2 Cluster Deployment
# ============================================================

$MasterPublicIP  = "15.134.121.250"
$Worker1PublicIP = "54.253.192.210"
$Worker2PublicIP = "54.252.191.145"

$MasterKey  = "C:\Users\hotru\Downloads\MASTER.pem"
$WorkersKey = "C:\Users\hotru\Downloads\WORKERS.pem"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  CustomerLens EC2 Cluster Automated Deployment" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Setup Master
Write-Host "`n[1/4] Preparing Master Node ($MasterPublicIP)..." -ForegroundColor Yellow
ssh -i $MasterKey -o StrictHostKeyChecking=no ubuntu@$MasterPublicIP @"
    mkdir -p ~/CustomerLens/backend/models ~/CustomerLens/backend/data
"@

Write-Host "  Copying .env.production to Master..." -ForegroundColor Gray
scp -i $MasterKey -o StrictHostKeyChecking=no "backend\.env.production" "ubuntu@${MasterPublicIP}:~/CustomerLens/backend/.env"

Write-Host "  Synchronizing models to Master (~45MB)..." -ForegroundColor Gray
scp -i $MasterKey -o StrictHostKeyChecking=no backend\models\*.onnx backend\models\*.task "ubuntu@${MasterPublicIP}:~/CustomerLens/backend/models/" 2>$null

Write-Host "  Executing setup-ec2.sh on Master..." -ForegroundColor Gray
ssh -i $MasterKey -o StrictHostKeyChecking=no ubuntu@$MasterPublicIP @"
    cd ~/CustomerLens && git pull origin main
    bash scripts/setup-ec2.sh master
"@

# 2. Setup Worker 1
Write-Host "`n[2/4] Preparing Worker 1 ($Worker1PublicIP)..." -ForegroundColor Yellow
ssh -i $WorkersKey -o StrictHostKeyChecking=no ubuntu@$Worker1PublicIP @"
    mkdir -p ~/CustomerLens/backend/models ~/CustomerLens/backend/data
"@

Write-Host "  Copying .env.production to Worker 1..." -ForegroundColor Gray
scp -i $WorkersKey -o StrictHostKeyChecking=no "backend\.env.production" "ubuntu@${Worker1PublicIP}:~/CustomerLens/backend/.env"

Write-Host "  Synchronizing models to Worker 1 (~45MB)..." -ForegroundColor Gray
scp -i $WorkersKey -o StrictHostKeyChecking=no backend\models\*.onnx backend\models\*.task "ubuntu@${Worker1PublicIP}:~/CustomerLens/backend/models/" 2>$null

Write-Host "  Executing setup-ec2.sh on Worker 1..." -ForegroundColor Gray
ssh -i $WorkersKey -o StrictHostKeyChecking=no ubuntu@$Worker1PublicIP @"
    cd ~/CustomerLens && git pull origin main
    bash scripts/setup-ec2.sh worker
"@

# 3. Setup Worker 2
Write-Host "`n[3/4] Preparing Worker 2 ($Worker2PublicIP)..." -ForegroundColor Yellow
ssh -i $WorkersKey -o StrictHostKeyChecking=no ubuntu@$Worker2PublicIP @"
    mkdir -p ~/CustomerLens/backend/models ~/CustomerLens/backend/data
"@

Write-Host "  Copying .env.production to Worker 2..." -ForegroundColor Gray
scp -i $WorkersKey -o StrictHostKeyChecking=no "backend\.env.production" "ubuntu@${Worker2PublicIP}:~/CustomerLens/backend/.env"

Write-Host "  Synchronizing models to Worker 2 (~45MB)..." -ForegroundColor Gray
scp -i $WorkersKey -o StrictHostKeyChecking=no backend\models\*.onnx backend\models\*.task "ubuntu@${Worker2PublicIP}:~/CustomerLens/backend/models/" 2>$null

Write-Host "  Executing setup-ec2.sh on Worker 2..." -ForegroundColor Gray
ssh -i $WorkersKey -o StrictHostKeyChecking=no ubuntu@$Worker2PublicIP @"
    cd ~/CustomerLens && git pull origin main
    bash scripts/setup-ec2.sh worker
"@

# 4. Verification
Write-Host "`n[4/4] Verifying Cluster Health..." -ForegroundColor Yellow
Start-Sleep -Seconds 5
try {
    $res = Invoke-RestMethod -Uri "http://${MasterPublicIP}:8000/" -TimeoutSec 10
    Write-Host "  [OK] Master API is ONLINE: http://${MasterPublicIP}:8000" -ForegroundColor Green
} catch {
    Write-Host "  [!] Master API check returned: $_" -ForegroundColor DarkYellow
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  Deployment Completed Successfully!" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
