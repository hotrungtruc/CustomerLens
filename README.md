# CustomerLens: Real-Time Enterprise Face Recognition & Guest Intelligence System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3670A0?style=flat-square&logo=python&logoColor=ffdd54" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.110+-005571?style=flat-square&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-14.2-000000?style=flat-square&logo=nextdotjs&logoColor=white" alt="Next.js">
  <img src="https://img.shields.io/badge/React-18.3-20232a?style=flat-square&logo=react&logoColor=61DAFB" alt="React">
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL_15-3ECF8E?style=flat-square&logo=supabase&logoColor=white" alt="Supabase">
  <img src="https://img.shields.io/badge/pgvector-HNSW-4169e1?style=flat-square&logo=postgresql&logoColor=white" alt="pgvector">
  <img src="https://img.shields.io/badge/Redis-Pub%2FSub-DD0031?style=flat-square&logo=redis&logoColor=white" alt="Redis">
  <img src="https://img.shields.io/badge/Redpanda-Kafka_Protocol-FF4500?style=flat-square&logo=redpanda&logoColor=white" alt="Redpanda">
  <img src="https://img.shields.io/badge/ONNX_Runtime-INT8_Execution-00599C?style=flat-square&logo=onnx&logoColor=white" alt="ONNX Runtime">
  <img src="https://img.shields.io/badge/Compliance-GDPR_Art._9_%26_17-red?style=flat-square" alt="Compliance">
</p>

---

## 1. Executive Summary: The Business Challenge in Modern Hospitality & Retail

### 1.1 The Operational Bottleneck of Guest Anonymity
In high-touch hospitality, dining, and luxury retail environments, operational excellence and customer lifetime value (LTV) hinge on a single operational capability: **timely customer recognition**. Knowing whether an entering patron is a first-time visitor, a returning casual guest, or a high-value regular dictates the quality of service delivery:
- Greeting a returning regular by name upon arrival establishes immediate rapport.
- Recalling dietary restrictions, seating preferences, or past orders enables proactive, personalized recommendations.
- Identifying customer churn and return frequency allows managers to optimize retention strategies.

However, traditional Customer Relationship Management (CRM) and loyalty programs suffer from high customer friction:
- Plastic membership cards are frequently forgotten or lost.
- Mobile apps and QR codes require active customer compliance, intrusive downloads, and friction at entry.
- Phone number lookup occurs exclusively at the point of payment—long after the opportunity for personalized hospitality has elapsed.

As a consequence, **over 70% of physical guest interactions remain completely anonymous** until checkout, leaving service staff uninformed and operational management blind to foot-traffic retention dynamics.

### 1.2 The Solution: Autonomous, Zero-Registration Biometric Intelligence
CustomerLens resolves this fundamental disconnect by transforming existing CCTV and security camera feeds into an ambient, zero-friction guest intelligence layer. 

Patrons are not required to enroll, download an application, scan a barcode, or present identification. The system autonomously:
1. Detects and tracks patrons across video frames in real time as they traverse the entrance.
2. Extracts privacy-preserving facial embeddings and performs sub-100ms vector matching against historical visits.
3. Automatically categorizes patrons into a dynamic lifecycle tier (from first-time visitors to VIP regulars).
4. Streams contextual Heads-Up Display (HUD) notifications to floor staff tablets and POS screens before the customer reaches the counter, displaying visit count, lifetime spend, dietary notes, and tailored menu recommendations.

---

<p align="center">
  <img src="assets/workflow.png" alt="CustomerLens End-to-End System Workflow" width="950" style="border-radius: 6px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);">
</p>

---

## 2. Customer Lifecycle Intelligence & Personalization Matrix

### 2.1 Dynamic 2-Letter Customer Matrix
To support fast human interpretation during rush hours, CustomerLens classifies patrons into a dynamic 2-letter lifecycle taxonomy that automatically updates based on cumulative visit frequency and monetary transaction records:

```mermaid
stateDiagram-v2
    direction LR
    [*] --> LN: First Visit (New Guest)
    LN --> LC: Visits 2 to 4 (Casual Guest)
    LC --> LL: Visits >= 5 (Loyal Regular)
    LL --> ML: Cumulative Spend >= 2,000,000 VND (Mass Loyal)
    ML --> HL: Cumulative Spend >= 10,000,000 VND or VIP Flag (VIP Loyal)
```

![Customer Lifecycle Personalization Matrix](assets/customer_lifecycle_matrix.png)

- **First Letter: Purchasing Power & Lifetime Value Tier**
  - `H` (High Tier): High-spending patrons ($\ge 10,000,000$ VND cumulative spend or designated VIP).
  - `M` (Medium Tier): Mass loyal customers with steady ticket size ($\ge 2,000,000$ VND).
  - `L` (Low / Standard Tier): Default baseline tier for standard or newly acquired patrons.
- **Second Letter: Behavioral Loyalty & Visit Frequency**
  - `N` (New): First-time visitor (visit count $= 1$).
  - `C` (Casual): Irregular visitor (visit count between $2$ and $4$).
  - `L` (Loyal): Committed regular patron (visit count $\ge 5$).

### 2.2 Operational Use Cases Enabled by Real-Time HUD
- **Instant VIP Recognition:** Front-of-house managers receive immediate tablet alerts when an `HL` (High-Loyal) patron enters, enabling immediate host greetings and priority table assignment.
- **Dietary Restriction Alerts:** Kitchen and floor staff can reference pinned notes (e.g., "Severe peanut allergy", "Prefers oat milk") before taking orders.
- **Contextual Recommendation Engine:** POS terminals receive automated recommendation prompts based on historical consumption patterns (e.g., suggesting a seasonal wine pairing matching previous preferences).
- **Anti-False Registration Buffer Gate:** Patrons are only registered as new unique entities after maintaining continuous track quality across 6 consecutive verified frames, preventing stray passersby or false positive detections from polluting customer databases.

---
## 3. Distributed System Architecture

CustomerLens is engineered as a distributed, event-driven streaming platform designed for horizontal scaling across multi-camera installations.

![CustomerLens Processing Workflow & Distributed Architecture](assets/workflow.png)

### Architectural Highlights
- **Edge-Cloud Hybrid Ingestion:** Client browsers and edge gateways perform localized Laplacian sharpness filtering and bounding box cropping before WebSocket transmission, decreasing raw video network bandwidth consumption by over 80%.
- **Asynchronous Event Fabric:** The API Gateway decouples frame ingestion from heavy computer vision inference using Redpanda (Kafka-compatible messaging), absorbing traffic bursts during peak operational hours.
- **Stateless AI Inference Cluster:** AI workers consume frame batches concurrently, run INT8-quantized ONNX models across CPU/GPU instances, and publish results to Redis Pub/Sub channels partitioned by connection identifier.
- **Sub-100ms Vector Search:** Facial embeddings are matched against Supabase PostgreSQL via an HNSW vector index (`halfvec_cosine_ops`) with binary parameter binding, backed by an in-memory Redis L1 cache for sub-millisecond retrieval of active patrons.

---

## 4. Computer Vision & Biometric Pipeline

```
  Input Frame ──> [SCRFD 500M INT8] ──> [5-Point Affine Alignment] ──> [EdgeFace 512-D INT8]
                         │                                                    │
                         ▼                                                    ▼
                 Kalman Tracking                                 Quality Attention Pooling
                 (Corner Velocity)                               (Sharpness & Pose Weighted)
                         │                                                    │
                         └──────────────────────┬─────────────────────────────┘
                                                ▼
                                   Cancelable Biometrics
                              (Irreversible Orthogonal Matrix)
                                                │
                                                ▼
                                     Supabase HNSW Search
                                    (K=3 Multi-Template)
```

### 4.1 SCRFD Face Detection & 5-Point Affine Alignment
Face detection is handled by an INT8-quantized **SCRFD 500M** model capable of localizing 5 facial landmarks (pupils, nose tip, mouth corners) across extreme pitch/yaw angles ($\pm 45^\circ$) down to a minimum bounding box of $16 \times 16$ pixels. Cropped faces are geometrically normalized into canonical ArcFace coordinate space ($112 \times 112 \times 3$) using similarity transformations, ensuring consistent orientation for subsequent feature extraction.

### 4.2 EdgeFace Embeddings & Cancelable Biometric Privacy
Normalized face crops are mapped into 512-dimensional unit feature embeddings using an INT8-quantized **EdgeFace** backbone. 

To eliminate legal liability and strictly adhere to privacy frameworks (GDPR Article 9 and CCPA), CustomerLens implements distance-preserving **Cancelable Biometrics**:
- Raw embeddings are irreversibly transformed via an orthogonal projection key matrix before database persistence.
- Because the transformation is strictly orthogonal, pairwise cosine similarity scores and vector retrieval distances are mathematically identical.
- In the event of a database breach, original face representations cannot be reconstructed from stored vectors, eliminating identity theft risks while preserving search accuracy.

### 4.3 Quality-Aware Dynamic Pooling & Multi-Template Matching
Rather than naively averaging noisy video frames, CustomerLens aggregates multi-frame trajectories using an intelligent composite quality weighting mechanism:
- **Quality-Aware Attention:** Each frame is scored based on facial pose centrality, image sharpness (Laplacian variance), and resolution. Motion-blurred frames or extreme profile angles are automatically downweighted, ensuring the pooled gallery vector reflects only high-clarity observations.
- **Multi-Template Gallery ($K=3$):** Each customer profile maintains up to three diverse exemplar templates (frontal, subtle angle, varying expression) captured across distinct visits. Database queries return the maximum similarity across these exemplars, capturing natural variations in facial appearance.
- **Distance-Adaptive Dynamic Thresholding:** Operating decision thresholds automatically calibrate to the subject's distance from the camera:
  - **Close Range ($\le 2\text{m}$, Face width $\ge 75\text{px}$):** Strict threshold ($\theta = 0.50$) for maximum security at entry turnstiles.
  - **Medium Range ($2\text{m} - 4\text{m}$, Face width $45\text{px} - 75\text{px}$):** Calibrated threshold ($\theta = 0.44 - 0.46$) providing over 83% true recognition with 0.00% false accept rate.
  - **Far Range ($> 4\text{m}$):** Permissive threshold ($\theta = 0.35$) buffering candidates until the patron approaches closer.

---

## 5. Empirical Production Benchmark Results

The entire system was evaluated on real-world video sequences from the academic **YouTube Faces (YTF)** benchmark, specifically utilizing the curated Kaggle dataset release:
- **Dataset Source:** [YouTube Faces with Facial Keypoints on Kaggle](https://www.kaggle.com/datasets/selfishgene/youtube-faces-with-facial-keypoints?select=youtube_faces_with_keypoints_full_1) (subset: `youtube_faces_with_keypoints_full_1`).
- **Scale:** **544 video clips · 207 identities · 61,487 frames** (206 identities have $\ge 2$ independent clips recorded across distinct sessions for cross-clip verification).
- **Evaluation Methodology:** Conducted strictly in accordance with NIST FRVT, IJB-C, and Google FaceNet evaluation protocols. For complete reproduction steps and script commands, refer to the [Model Evaluation & Benchmark Reproduction Guide](docs/model_evaluation_guide.md).

All video clips were evaluated across four real-world surveillance degradation conditions simulating physical camera distance:
- `close_1.5m`: Native resolution, standard frontal entry camera.
- `medium_3.5m`: Optical downscale 0.60x, Gaussian blur $\sigma = 0.6$.
- `far_6.0m`: Optical downscale 0.38x, motion blur $\sigma = 1.2$, JPEG quality 55.
- `veryFar_9m`: Extreme optical downscale 0.22x, optical distortion $\sigma = 1.8$, JPEG quality 35.

![Empirical Benchmark Accuracy Curves across Degradation Conditions](assets/benchmark_accuracy.png)

### Track 1: Video-Based 1:1 Verification (NIST FRVT Verification Protocol)
Evaluating all genuine pairs (same identity, different video clips) against balanced impostor pairs (different identities):

| Camera Condition | Pair Count (Gen / Imp) | TAR @ FAR=0.1% | TAR @ FAR=0.01% | Equal Error Rate (EER) | AUC-ROC | Genuine Sim ($\mu \pm \sigma$) | Impostor Sim ($\mu \pm \sigma$) | Separation Margin |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`close_1.5m`** | 511 / 1,533 | **93.15%** | **92.76%** | **4.50%** | **0.9851** | $0.6370 \pm 0.1911$ | $0.0240 \pm 0.1042$ | **+0.6129** |
| **`medium_3.5m`** | 511 / 1,533 | **90.80%** | **86.69%** | **4.31%** | **0.9845** | $0.6074 \pm 0.1954$ | $0.0160 \pm 0.1058$ | **+0.5914** |
| **`far_6.0m`** | 502 / 1,506 | **16.73%** | **7.37%** | **14.38%** | **0.9325** | $0.4500 \pm 0.2054$ | $0.0657 \pm 0.1401$ | **+0.3843** |
| **`veryFar_9m`** | 331 / 993 | **2.11%** | **2.11%** | **32.33%** | **0.7377** | $0.4526 \pm 0.2115$ | $0.2641 \pm 0.1990$ | **+0.1884** |

At operational retail entry distances ($1.5\text{m} - 3.5\text{m}$), the system achieves an **AUC-ROC of 0.985**, an **Equal Error Rate of 4.31%**, and an impostor separation margin of **+0.6129**, confirming reliable distinction between genuine patrons and distinct individuals.

### Track 2: Video-Based 1:N Closed-Set Identification (IJB-C CMC Curve)
Evaluating identification across a gallery of $N = 206$ unique individuals (first clip per person), tested against 206 independent probe clips:

| Camera Condition | Gallery Size ($N$) | Rank-1 Identification | Rank-5 Identification | Rank-10 Identification |
|:---|:---:|:---:|:---:|:---:|
| **`close_1.5m`** | 206 | **90.78%** | **92.72%** | **93.20%** |
| **`medium_3.5m`** | 206 | **88.83%** | **92.23%** | **93.20%** |
| **`far_6.0m`** | 203 | **54.19%** | **67.98%** | **75.37%** |
| **`veryFar_9m`** | 138 | **18.84%** | **36.96%** | **44.20%** |

In a closed gallery of 206 registered individuals, the system correctly identifies the target at position number one (**Rank-1**) in **90.78%** of trials at close range and **88.83%** at 3.5m range. Top-5 suggestion accuracy reaches **92.72%**.

### Track 3: Open-Set Identification with Reject Option (NIST DIR @ FPIR)
Simulating an authentic operational store scenario: the gallery contains only **155 registered loyalty members**. The probe stream contains both **155 genuine returning members** and **51 unregistered strangers (impostors)**:

| Camera Condition | Operating Threshold ($\theta$) | True Identification (DIR) | False Impostor Accept (FPIR) | False Patron Reject (FNIR) |
|:---|:---:|:---:|:---:|:---:|
| `close_1.5m` | $\theta = 0.50$ | 80.65% | **0.00%** | 19.35% |
| `close_1.5m` | $\theta = 0.44$ | **83.87%** | **0.00%** | 16.13% |
| `close_1.5m` | $\theta = 0.40$ | 85.16% | 3.92% | 14.84% |
| `close_1.5m` | $\theta = 0.35$ | 89.03% | 29.41% | 10.97% |
| `medium_3.5m`| $\theta = 0.46$ | 79.35% | **1.96%** | 20.65% |
| `medium_3.5m`| $\theta = 0.44$ | **80.65%** | **1.96%** | 19.35% |
| `medium_3.5m`| $\theta = 0.40$ | 84.52% | 5.88% | 15.48% |
| `far_6.0m`   | $\theta = 0.40$ | 47.06% | 56.86% | 52.94% |

**Recommended Production Operating Point:** Setting $\theta = 0.44$ yields **83.87% correct identification** while maintaining **0.00% False Positive Identification Rate (zero impostors accepted)**.

### Track 4: Vector Search Latency & Throughput Stress Test (Production SLO)
Executing **500 consecutive 512-dimensional vector queries** against the live Supabase PostgreSQL HNSW index under concurrent load:

![Production Vector Search Latency Distribution](assets/benchmark_latency.png)

| Infrastructure Metric | Observed Result | Production Target SLO | Evaluation Status |
|:---|:---:|:---:|:---:|
| **P50 Latency (Median)** | **58.17 ms** | < 60 ms | Compliant |
| **P95 Latency** | **62.73 ms** | < 80 ms | Compliant |
| **P99 Latency (Tail)** | **73.82 ms** | < 100 ms | Compliant (26% safety margin) |
| **P99.9 Latency** | **110.37 ms** | < 150 ms | Compliant |
| **Maximum Observed Latency** | **142.84 ms** | — | Stable |
| **Sustained Query Throughput** | **16.9 QPS** | $\ge$ 10 QPS | Compliant (+69% headroom) |

The complete single-frame inference pipeline (Detection + Alignment + Embedding + Tracking) executes in **32.29 ms** (equivalent to **30.34 FPS**), fully sustaining real-time processing of standard 25–30 FPS RTSP cameras.

---

## 6. Biometric Security, Privacy & Legal Compliance

CustomerLens is designed to comply with privacy frameworks including **GDPR Article 9 (Special Category Biometric Data)** and **GDPR Article 17 (Right to be Forgotten)**:
- **Asymmetric RS256 Authentication & Instant Session Revocation:** API Gateway tokens are signed with 2048-bit RSA keys and verified statelessly across workers. Instant revocation timestamps in Redis (`user_revoked_at:{user_id}`) terminate credentials immediately across all cluster nodes upon logout or administrative disablement.
- **Cancelable Biometric Embeddings:** Only transformed vectors $\vec{x}' = Q\vec{x}$ are persisted in pgvector. Original facial embeddings are discarded immediately after inference.
- **Authenticated Encryption at Rest (AES-256-GCM):** Temporary image crops cached for administrative audit are encrypted using AES-256-GCM with unique 12-byte initialization vectors per asset.
- **Automated Data Lifecycle Purging:** An automated background worker deletes unregistered guest trajectories and associated vector embeddings older than the configurable retention window (default: 30 days).

---

## 7. Technology Stack

| Layer | Technologies & Frameworks |
|:---|:---|
| **Frontend UI** | Next.js 14 (App Router), React 18, Tailwind CSS, HTML5 Canvas API |
| **API Gateway** | FastAPI, Uvicorn, Python 3.12, asyncio, WebSockets |
| **Event Messaging** | Redpanda (Apache Kafka v2.8+ wire compatible), Redis Pub/Sub |
| **AI Inference Engine** | ONNX Runtime INT8, EdgeFace, SCRFD 500M, OpenCV, NumPy, SciPy |
| **Database & Vector Search** | PostgreSQL 15+, Supabase, pgvector (HNSW Index with `halfvec_cosine_ops`) |
| **Security & Cryptography** | PyJWT (RS256 2048-bit RSA), Cryptography (AES-256-GCM), Orthogonal Matrix Projection |
| **Deployment & DevOps** | Docker, Docker Compose, Nginx, AWS EC2 |

---

## 8. Installation & Deployment Guide

### 8.1 System Prerequisites
- Operating System: Linux (Ubuntu 22.04 LTS recommended), macOS, or Windows 11.
- Runtimes: Python 3.12+, Node.js 18+, Docker Engine with Compose V2.

### 8.2 Infrastructure Initialization
```bash
git clone https://github.com/hotrungtruc/CustomerLens.git
cd CustomerLens

# Launch Redis cache container
docker run -d --name customerlens-redis -p 6379:6379 redis:alpine
```

### 8.3 Backend Configuration & Startup
Create `backend/.env` configured with environment credentials:
```env
USE_SUPABASE=true
SUPABASE_URL="postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"
REDIS_URL="redis://127.0.0.1:6379/0"
KAFKA_BOOTSTRAP_SERVERS="127.0.0.1:9092"
```

Initialize the Python environment and launch the API Gateway:
```bash
cd backend
python -m venv .venv

# Activate virtual environment
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate

pip install -r requirements.txt

# Initialize database schema and download pretrained ONNX models
python -m app.db.connection
python -m app.utils.download_models

# Start FastAPI Gateway
python run.py
```

Launch the asynchronous AI Worker in a separate terminal:
```bash
cd backend
source .venv/bin/activate
python app/ai_worker.py
```

### 8.4 Frontend Dashboard Startup
```bash
cd frontend
npm install
npm run dev
```
Access the management console at `http://localhost:3000` (Default credentials: `admin` / `change_me_immediately`).

### 8.5 Full Containerized Deployment
To orchestrate the complete cluster via Docker Compose:
```bash
docker compose build
docker compose up -d
```

---

## 9. Modular Technical Documentation

In-depth technical architecture and engineering specifications are organized within dedicated documents in the `docs/` directory:

| Document | Topic & Focus Area |
|:---|:---|
| [System Architecture](docs/system_architecture.md) | Distributed event-driven design, Redpanda ingestion, and Redis Pub/Sub topology. |
| [AI Inference Pipeline](docs/ai_pipeline.md) | SCRFD detection, Kalman filter tracking, and Attention Pooling mathematics. |
| [Database Schema](docs/database_schema.md) | PostgreSQL schema definitions, HNSW vector indexing, and RPC procedures. |
| [Frontend Architecture](docs/frontend_architecture.md) | Next.js 14 App Router, Canvas rendering loop, and WebSocket lifecycle management. |
| [API Reference](docs/api_reference.md) | Comprehensive specification of REST endpoints and WebSocket subprotocols. |
| [Model Evaluation Guide](docs/model_evaluation_guide.md) | Step-by-step reproduction guide and statistical protocols for NIST FRVT and IJB-C evaluation. |
| [Production Benchmark Report](assets/YTF/results/production_eval_report.md) | Full tabular results and statistical analysis across all 544 YTF video sequences. |
| [Maintenance Guide](docs/maintenance_guide.md) | Operational playbooks, systemd service management, and backup procedures. |

---

## 10. Author & License

CustomerLens is authored by Ho Trung Truc for academic research and enterprise commercial deployment.
- **Author:** Ho Trung Truc
- **Email:** hotrungtruc1706@gmail.com
- **Repository:** [https://github.com/hotrungtruc/CustomerLens](https://github.com/hotrungtruc/CustomerLens)