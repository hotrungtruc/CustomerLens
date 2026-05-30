# Smart Front-door AI

A restaurant entrance camera system that recognizes and identifies customers in real time. The stack uses a FastAPI/Uvicorn backend (MJPEG streaming, SQLite) and a Next.js frontend.

![Demo](frontend/public/demo_05_21.jpg)

## Features

- Real-time face detection and matching via embeddings
- Customer profiles stored in SQLite
- Decoupled React UI for future dashboards
- Stable MJPEG stream for low-latency video

## Model

- **Detection**: MediaPipe Tasks API (automatic, optimized)
  - `face_landmarker.task` (auto-downloaded, highest accuracy)
  - Fallback: MediaPipe Solutions API (built-in)
  - Last resort: OpenCV Haar Cascade (if MediaPipe unavailable)
- **Recognition/Embedding**: MobileFaceNet ONNX
  - `mobilefacenet_int8.onnx` (preferred, optimized)
  - `w600k_mbf.onnx` (fallback if int8 not supported)

### Model Download
`download_models` automatically downloads all required models:
- ✅ `w600k_mbf.onnx` - embedding model (from GitHub)
- ✅ `face_landmarker.task` - face detection model (from Google Storage)
- ✅ `mobilefacenet_int8.onnx` - auto-generated from w600k_mbf if supported

No manual downloads needed! Everything is automatic.

## System Requirements

- **Python**: 3.8+
- **Camera**: USB/built-in webcam (optional for encoding generation)
- **RAM**: 4GB minimum (8GB+ recommended for smooth operation)
- **Dependencies**: All Python packages auto-installed via `pip install -r backend\requirements.txt`

## Project structure

```
face-recognition-system/
├── backend/
│   ├── app/
│   │   ├── api/              # API routes + streaming
│   │   ├── core/             # Face recognition logic
│   │   ├── db/               # SQLite access
│   │   └── utils/            # Encodings + model downloader
│   ├── data/
│   │   ├── encodings/
│   │   ├── images/
│   │   └── face_attendance.db
│   ├── models/               # ONNX models
│   ├── config.py
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── pages/
│   │   └── services/
│   ├── public/
│   ├── package.json
│   └── tailwind.config.js
└── README.md
```

## Quick start (Windows)

### 1) Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
```

Download models and prepare data:

```bash
cd backend
python -m app.utils.download_models
python -m app.db.seed_data
python -m app.utils.encodings
```

**Note**: The backend automatically handles:
- ✅ All models auto-downloaded
- ✅ Default: MediaPipe Tasks API (best accuracy)
- ✅ ONNX int8 → float model fallback if not supported
- ✅ Fallback: MediaPipe Solutions API → OpenCV if needed

`download_models` downloads `w600k_mbf.onnx`, `face_landmarker.task`, and attempts to create an int8 version (`mobilefacenet_int8.onnx`) for optimized inference. If int8 quantization fails, the float version is used automatically.

Run the backend with the official ASGI entry point:

```bash
python backend/run.py
```

Backend runs at `http://localhost:8000`.

### 2) Frontend

Open a new terminal:

```bash
cd frontend
npm install #Once time
npm run dev
```

Frontend runs at `http://localhost:3000`.

By default the frontend calls `http://localhost:8000`. To change it, create `frontend\.env.local`:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Then restart `npm run dev`.

## API endpoints

- `GET /video_feed`: MJPEG stream from the camera
- `GET /api/customer_info`: current customer profile
- `POST /api/check_in`: check-in the current customer

## Preparing customer photos

1. Put images in: `backend/data/images/`
2. File name: `{customer_id}.jpg` or `.png`
3. After adding images, re-generate encodings:

```bash
cd backend
python -m app.utils.encodings
```

## Quick configuration

- Camera index, similarity threshold, and cooldown live in [backend/config.py](backend/config.py)
- To change backend port, edit `host`/`port` in [backend/run.py](backend/run.py)

## Known Issues & Workarounds

### ONNX Runtime Compatibility
- **Issue**: `NotImplemented: Could not find an implementation for ConvInteger(10)` error
- **Cause**: Your ONNX Runtime version doesn't support int8 quantized models
- **Solution**: ✅ **Automatic fallback** - The system automatically detects this error and switches to the float model (`w600k_mbf.onnx`)
- **What to expect**: You'll see a warning message. The system continues working normally with slightly higher memory usage.

### MediaPipe Face Detection
- **Automatic**: `face_landmarker.task` is auto-downloaded by `download_models`
- **Default**: MediaPipe Tasks API (highest accuracy, optimized)
- **Fallback order**:
  1. MediaPipe Tasks API ← **Used by default** (auto-downloaded)
  2. MediaPipe Solutions API (built-in fallback)
  3. OpenCV Haar Cascade (only if MediaPipe not installed)
- **What to expect**: System works out of the box with best accuracy. Check console to confirm which method is used.

### Face Detection Quality
- **Issue**: Small faces or faces from certain angles not detected
- **Cause**: Strict quality thresholds for bounding box size
- **Solution**: ✅ **Flexible quality checks** - The system uses adaptive thresholds (min 50×50 px) with embedding-based validation

## Troubleshooting

- **Cannot access camera**: Close other apps using the webcam
- **No customer detected**: Run `python -m app.utils.encodings` to re-generate face embeddings
- **Model error**: Run `python -m app.utils.download_models` to download all required models
- **Face not detected in images**: Ensure images have clear, frontal faces; try different angles or ensure minimum 50×50 pixel face size
- **Models not downloading**: Check internet connection and ensure sufficient storage space
- **Still having issues?**: Check the console output. You should see "Using MediaPipe Tasks API for face detection" or "Using MediaPipe Solutions API for face detection"

