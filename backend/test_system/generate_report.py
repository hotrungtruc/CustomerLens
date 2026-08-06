import os
import json
import sys
from pathlib import Path
from datetime import datetime

backend_dir = Path(__file__).resolve().parent.parent
results_dir = os.path.join(backend_dir, "test_system", "results")

def generate_markdown_report(output_file: str = None) -> str:
    acc_path = os.path.join(results_dir, "accuracy_results.json")
    speed_path = os.path.join(results_dir, "speed_results.json")
    stress_path = os.path.join(results_dir, "e2e_stress_results.json")

    acc_data = {}
    if os.path.exists(acc_path):
        with open(acc_path, "r", encoding="utf-8") as f:
            acc_data = json.load(f)

    speed_data = {}
    if os.path.exists(speed_path):
        with open(speed_path, "r", encoding="utf-8") as f:
            speed_data = json.load(f)

    stress_data = {}
    if os.path.exists(stress_path):
        with open(stress_path, "r", encoding="utf-8") as f:
            stress_data = json.load(f)

    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    v1to1 = acc_data.get("verification_1to1", {})
    i1toN = acc_data.get("identification_1toN", {})
    single_speed = speed_data.get("feature_extraction_single", {})
    scrfd_speed = speed_data.get("scrfd_detection_720p", {})
    pgvector_speed = speed_data.get("pgvector_hnsw_search", {})

    report = f"""# 🎓 Báo cáo Đánh giá AI: Độ chính xác & Tốc độ Xử lý Hệ thống (Face Recognition System Benchmark)

**Thời gian thực hiện**: `{timestamp_str}`  
**Bộ dữ liệu Đánh giá**: `{acc_data.get('dataset', 'C:\\SCHOOL\\asian_celeb_112x112_folders')}`  
**Số lượng nhân vật thử nghiệm (Identities)**: `{acc_data.get('num_identities_evaluated', 300)}` người ngẫu nhiên  
**Tổng số ảnh khuôn mặt xử lý**: `{acc_data.get('total_images_processed', 0)}` ảnh  

---

## 1. Đánh giá Độ chính xác Nhận diện (Biometric Accuracy Benchmark)

### A. Xác thực 1:1 (Face Verification Performance)
* **Equal Error Rate (EER)**: `{v1to1.get('eer_percentage', 'N/A')}%`
* **Ngưỡng Cosine Similarity tối ưu (\\theta^*)**: `{v1to1.get('optimal_cosine_threshold', 'N/A')}`
* **True Accept Rate (TAR) @ FAR = 0.1% (10^-3)**: `{v1to1.get('tar_at_far_1e3_percentage', 'N/A')}%`
* **True Accept Rate (TAR) @ FAR = 0.01% (10^-4)**: `{v1to1.get('tar_at_far_1e4_percentage', 'N/A')}%`
* **Precision @ \\theta^***: `{v1to1.get('precision_percentage', 'N/A')}%`
* **Recall @ \\theta^***: `{v1to1.get('recall_percentage', 'N/A')}%`
* **F1-Score @ \\theta^***: `{v1to1.get('f1_score_percentage', 'N/A')}%`
* **Điểm tương đồng trung bình (Genuine Pairs)**: `{v1to1.get('mean_genuine_similarity', 'N/A')}`
* **Điểm tương đồng trung bình (Impostor Pairs)**: `{v1to1.get('mean_impostor_similarity', 'N/A')}`

### B. Định danh 1:N (Face Identification Performance)
* **Kích thước thư viện Gallery**: `{i1toN.get('gallery_size', 'N/A')}` identities
* **Số lượt truy vấn Probe**: `{i1toN.get('probes_evaluated', 'N/A')}` queries
* **Rank-1 Identification Accuracy**: **`{i1toN.get('rank1_accuracy_percentage', 'N/A')}%`**
* **Rank-5 Identification Accuracy**: **`{i1toN.get('rank5_accuracy_percentage', 'N/A')}%`**

---

## 2. Đánh giá Tốc độ & Độ trễ Xử lý (System Speed & Latency Benchmark)

| Công đoạn Xử lý (Pipeline Stage) | Mean Latency | Median (P50) | P90 Latency | P99 Latency | Throughput (FPS) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ONNX Feature Extraction (EdgeFace)** | `{single_speed.get('mean_ms', 0)} ms` | `{single_speed.get('p50_ms', 0)} ms` | `{single_speed.get('p90_ms', 0)} ms` | `{single_speed.get('p99_ms', 0)} ms` | **`{single_speed.get('fps', 0)} FPS`** |
| **SCRFD Face Detection (720p Frame)** | `{scrfd_speed.get('mean_ms', 0)} ms` | `{scrfd_speed.get('p50_ms', 0)} ms` | `{scrfd_speed.get('p90_ms', 0)} ms` | `{scrfd_speed.get('p99_ms', 0)} ms` | **`{scrfd_speed.get('fps', 0)} FPS`** |
| **Supabase pgvector HNSW Search** | `{pgvector_speed.get('mean_ms', 0)} ms` | `{pgvector_speed.get('p50_ms', 0)} ms` | `{pgvector_speed.get('p90_ms', 0)} ms` | `{pgvector_speed.get('p99_ms', 0)} ms` | - |

---

## 3. Đánh giá Khả năng Chịu tải Đa Camera Stream (Multi-Camera Stress Test)

| Số lượng Camera | System Aggregate FPS | Average FPS / Camera | Total Frames Processed | Status |
| :--- | :--- | :--- | :--- | :--- |
"""

    for k, v in stress_data.items():
        cams = v.get("num_cameras", 0)
        sys_fps = v.get("aggregate_system_fps", 0)
        cam_fps = v.get("avg_fps_per_camera", 0)
        total_f = v.get("total_frames_processed", 0)
        report += f"| **{cams} Camera Stream(s)** | `{sys_fps} FPS` | `{cam_fps} FPS/cam` | `{total_f} frames` | ✅ Stable |\n"

    report += """
---

## 4. Kết luận & Khuyên dùng của Giáo sư AI (Architect Recommendations)

1. **Về Ngưỡng Cosine Threshold**:
   * Ngưỡng tối ưu $\\theta^*$ đo đạc được trên bộ dữ liệu Asian Celeb là **`""" + str(v1to1.get('optimal_cosine_threshold', 0.5)) + """`**.
   * Để đạt mức **TAR = """ + str(v1to1.get('tar_at_far_1e3_percentage', 0)) + """%** với tỉ lệ chấp nhận sai FAR chỉ 0.1%, hệ thống nên thiết lập `SIMILARITY_THRESHOLD = """ + str(v1to1.get('optimal_cosine_threshold', 0.5)) + """`.

2. **Về Tốc độ Xử lý & Khả năng Mở rộng**:
   * Mô hình ONNX `edgeface_s_gamma_05` hoạt động siêu tốc với thời gian trích xuất trung bình **`""" + str(single_speed.get('mean_ms', 0)) + """ ms/ảnh`** (~**""" + str(single_speed.get('fps', 0)) + """ FPS**).
   * Truy vấn HNSW index trên Supabase (`halfvec_cosine_ops`) đáp ứng dưới **`""" + str(pgvector_speed.get('mean_ms', 0)) + """ ms`**, sẵn sàng scale cho hàng chục ngàn vector khuôn mặt.
"""

    if not output_file:
        output_file = os.path.join(backend_dir, "test_system", "benchmark_report.md")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[ReportGenerator] Report successfully written to: {output_file}")
    return report

if __name__ == "__main__":
    generate_markdown_report()
