# 🧪 CustomerLens AI Test System: Face Recognition Accuracy & Speed Benchmarking

Hệ thống kiểm thử và đánh giá chuyên sâu độ chính xác (Biometrics Evaluation) và tốc độ xử lý (Latency & Throughput Benchmark) cho CustomerLens.

---

## 📁 Cấu trúc Thư mục

```text
backend/test_system/
├── dataset_loader.py       # Tải và trích xuất dữ liệu từ C:\SCHOOL\asian_celeb_112x112_folders
├── benchmark_accuracy.py   # Đo EER, TAR@FAR, Rank-1/Rank-5 Accuracy, Cosine Threshold
├── benchmark_speed.py      # Đo ONNX Inference Latency (ms), FPS, SCRFD Detection, Supabase HNSW Search
├── benchmark_e2e_stress.py # Đánh giá throughput hệ thống dưới tải 1 -> 4 -> 8 camera stream đồng thời
├── generate_report.py      # Tổng hợp dữ liệu và sinh báo cáo Markdown tự động
├── run_all_benchmarks.py   # CLI duy nhất chạy toàn bộ quy trình kiểm thử
├── README.md               # Hướng dẫn sử dụng
└── results/                # Lưu trữ kết quả đầu ra JSON và Báo cáo Markdown
```

---

## 🚀 Hướng dẫn Chạy Kiểm thử

### 1. Chạy Toàn bộ Kiểm thử (Mặc định: 300 người ngẫu nhiên)
```bash
python backend/test_system/run_all_benchmarks.py --num-identities 300
```

### 2. Tùy chọn Số lượng Người kiểm thử
```bash
# Thử nghiệm nhanh với 100 người
python backend/test_system/run_all_benchmarks.py --num-identities 100

# Thử nghiệm quy mô lớn với 1,000 người
python backend/test_system/run_all_benchmarks.py --num-identities 1000
```

### 3. Chạy Từng Bài Test Riêng Lẻ
* **Chỉ test Độ chính xác**:
  ```bash
  python backend/test_system/benchmark_accuracy.py
  ```
* **Chỉ test Tốc độ**:
  ```bash
  python backend/test_system/benchmark_speed.py
  ```
* **Chỉ test Stress Test Đa Camera**:
  ```bash
  python backend/test_system/benchmark_e2e_stress.py
  ```

---

## 📊 Kết quả Đầu ra
Sau khi kết thúc kiểm thử, báo cáo tổng hợp chi tiết sẽ được tự động tạo tại:
`backend/test_system/benchmark_report.md`
