# HƯỚNG DẪN TRIỂN KHAI CỤM BACKEND CUSTOMERLENS LÊN AWS EC2 (MASTER - WORKER CLUSTER)

Tài liệu hướng dẫn chi tiết quy trình triển khai phân tán cụm hệ thống **CustomerLens** trên 3 máy chủ ảo AWS EC2 bao gồm 1 Master Node (API Gateway, Redis, Redpanda) và 2 Worker Nodes (AI Inference: EdgeFace + SCRFD).

---

## 1. THÔNG SỐ CỤM MÁY CHỦ EC2 HIỆN TẠI

| Node | Vai trò | Public IP | Private IP (VPC) | SSH Key File | Cấu hình RAM / Swap |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Master Node** | API Gateway, Redis, Redpanda Broker | `15.134.121.250` | `172.31.9.172` | `C:\Users\hotru\Downloads\MASTER.pem` | 1GB RAM + 2GB Swap |
| **Worker 1** | AI Processing (EdgeFace + SCRFD) | `54.253.192.210` | `172.31.2.93` | `C:\Users\hotru\Downloads\WORKERS.pem` | 1GB RAM + 2GB Swap |
| **Worker 2** | AI Processing (EdgeFace + SCRFD) | `54.252.191.145` | `172.31.4.195` | `C:\Users\hotru\Downloads\WORKERS.pem` | 1GB RAM + 2GB Swap |

---

## 2. CẤU HÌNH AWS SECURITY GROUP (BẮT BUỘC)

Để cụm máy chủ giao tiếp thông suốt trong nội bộ mạng VPC (`172.31.0.0/20`), cần đảm bảo cấu hình các Inbound Rules trên AWS Console:

### 2.1. Master Security Group:
* **Port 22 (SSH):** Inbound từ `0.0.0.0/0` hoặc IP của bạn.
* **Port 8000 (FastAPI REST & WebSocket):** Inbound từ `0.0.0.0/0` (để Frontend và Camera bên ngoài kết nối tới).
* **Port 6379 (Redis Pub/Sub):** Inbound từ `172.31.0.0/16` (hoặc gắn Security Group của Worker) để 2 Worker gửi/nhận kết quả.
* **Port 9092 (Redpanda/Kafka):** Inbound từ `172.31.0.0/16` (hoặc gắn Security Group của Worker) để 2 Worker nhận stream frames.

### 2.2. Worker Security Group (`sg-worker`):
* **Port 22 (SSH):** Inbound từ `0.0.0.0/0` hoặc IP của bạn (để quản trị / deploy).
* **Outbound Rules:** All traffic `0.0.0.0/0` (để tải package và tải model nếu cần).

---

## 3. TRIỂN KHAI NHANH TỰ ĐỘNG (1-CLICK DEPLOYMENT)

Hệ thống đã chuẩn bị sẵn kịch bản PowerShell tự động hóa toàn bộ quá trình:
- Đồng bộ biến môi trường `backend/.env.production` lên cả 3 máy.
- Đồng bộ các file mô hình ONNX (~45MB) từ máy local lên thư mục `backend/models/`.
- Cập nhật Git code mới nhất từ nhánh `main`.
- Tự động cài đặt Docker (nếu máy mới) và kích hoạt các container tương ứng theo vai trò.

### Chạy từ Terminal trên máy Local:
```powershell
# Chạy script PowerShell tự động
.\scripts\deploy-ec2.ps1
```

Hoặc chỉ copy biến môi trường qua Batch script:
```cmd
.\deploy_env.bat
```

---

## 4. QUY TRÌNH TRIỂN KHAI THỦ CÔNG TỪNG MÁY (KHI CẦN DEBUG)

### 4.1. Cấu hình trên Master Node (`15.134.121.250`):
```bash
# SSH vào Master
ssh -i "C:\Users\hotru\Downloads\MASTER.pem" ubuntu@15.134.121.250

# Clone mã nguồn (nếu máy mới)
git clone https://github.com/hotrungtruc/CustomerLens.git
cd CustomerLens

# Chạy kịch bản khởi tạo Master
bash scripts/setup-ec2.sh master

# Kiểm tra container đang chạy
sudo docker compose ps
```

### 4.2. Cấu hình trên Worker Node 1 & 2:
```bash
# SSH vào Worker 1
ssh -i "C:\Users\hotru\Downloads\WORKERS.pem" ubuntu@54.253.192.210

# Clone mã nguồn & chạy kịch bản Worker
git clone https://github.com/hotrungtruc/CustomerLens.git
cd CustomerLens
bash scripts/setup-ec2.sh worker

# Kiểm tra container Worker
sudo docker compose -f docker-compose.worker.yml ps
```
*(Thực hiện tương tự cho Worker 2 tại IP `54.252.191.145`)*.

---

## 5. KIỂM TRA & XÁC NHẬN HOẠT ĐỘNG (HEALTHCHECK)

1. **Kiểm tra API Gateway:**
   ```bash
   curl http://15.134.121.250:8000/
   # Kết quả mong đợi: {"status": "ok", "message": "CustomerLens API running"}
   ```

2. **Xem Logs Master:**
   ```bash
   sudo docker compose logs -f backend
   ```

3. **Xem Logs AI Worker trên Worker Nodes:**
   ```bash
   sudo docker compose -f docker-compose.worker.yml logs -f ai_worker
   ```

4. **Kiểm tra Tài nguyên RAM / Swap:**
   ```bash
   free -h
   # Cả 3 máy đều có 2.0Gi Swap để bảo vệ an toàn OOM khi tải ONNX model
   ```
