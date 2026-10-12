"""
CustomerLens YTF Speed, Latency & Stress Test Benchmark.
Measures:
1. Detection Latency (SCRFD)
2. Recognition Latency (EdgeFace INT8)
3. Biometric Security & Search Latency (Orthogonal Projection + Vector Search)
4. Tracking & Kalman Latency (GuestTrackManager)
5. End-to-End Latency & Throughput (FPS)
6. Percentile Metrics: Min, Mean, Median, P95, P99, Max
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, List
import numpy as np
import cv2

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from app.core.insight_embedding import InsightEmbedder
from app.core.tracking.guest_tracker import GuestTrackManager
from app.core.biometric_security import biometric_protector
from test_system.ytf_dataset_loader import load_ytf_video, YTF_DEFAULT_DIR

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def calculate_stats(timings_ms: List[float]) -> Dict[str, float]:
    arr = np.array(timings_ms, dtype=np.float64)
    return {
        "min_ms": round(float(np.min(arr)), 2),
        "mean_ms": round(float(np.mean(arr)), 2),
        "median_ms": round(float(np.median(arr)), 2),
        "p95_ms": round(float(np.percentile(arr, 95)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
        "max_ms": round(float(np.max(arr)), 2),
    }


def run_speed_stress_benchmark(
    video_path: str | None = None,
    num_frames: int = 120,
    output_json: str | None = None,
) -> Dict:
    print("\n" + "=" * 75)
    print("  CUSTOMERLENS SPEED, LATENCY & STRESS BENCHMARK (YTF)")
    print("=" * 75)

    default_vid = os.path.join(YTF_DEFAULT_DIR, "Aaron_Eckhart_0.npz")
    target_vid = video_path or default_vid
    print(f"  - Target Dataset Sequence: {os.path.basename(target_vid)}")

    data = load_ytf_video(target_vid)
    available_frames = data["num_frames"]
    total_frames = min(available_frames, num_frames)
    print(f"  - Frames to benchmark: {total_frames} (Available in video: {available_frames})")

    embedder = InsightEmbedder()
    tracker = GuestTrackManager(
        buffer_size=3,
        guest_creation_buffer_size=6,
        similarity_threshold=0.55,
        iou_threshold=0.35,
        min_bbox_size=40,
        min_detection_score=0.70,
        guest_prefix="LN",
    )

    # Warmup
    print("\n[Warmup] Running 5 warmup cycles to prime ONNX runtime execution providers...")
    dummy_rgb = data["colorImages"][:, :, :, 0]
    dummy_bgr = cv2.cvtColor(dummy_rgb, cv2.COLOR_RGB2BGR)
    for _ in range(5):
        w_boxes, w_landmarks, _ = embedder.detect(dummy_bgr)
        if len(w_boxes) > 0:
            embedder.get_embedding(dummy_bgr, w_landmarks[0])

    det_times = []
    emb_times = []
    bio_times = []
    track_times = []
    e2e_times = []

    print(f"\n[Benchmarking] Processing {total_frames} consecutive video frames...")
    start_total_wall = time.perf_counter()

    for idx in range(total_frames):
        frame_rgb = data["colorImages"][:, :, :, idx % available_frames]
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        t_frame_start = time.perf_counter()

        # Step 1: SCRFD Face Detection & 5-point Landmarks
        t0 = time.perf_counter()
        boxes, landmarks, scores = embedder.detect(frame_bgr)
        t_det = (time.perf_counter() - t0) * 1000.0
        det_times.append(t_det)

        # Step 2: EdgeFace Recognition & Alignment
        face_records = []
        t0 = time.perf_counter()
        for i, box in enumerate(boxes):
            emb = embedder.get_embedding(frame_bgr, landmarks[i])
            face_records.append({
                "bbox": box.tolist(),
                "embedding": emb,
                "score": float(scores[i]),
                "quality_ok": True,
                "guest_quality_ok": True,
            })
        t_emb = (time.perf_counter() - t0) * 1000.0
        emb_times.append(t_emb)

        # Step 3: Biometric Security Projection
        t0 = time.perf_counter()
        for rec in face_records:
            if rec["embedding"] is not None:
                _ = biometric_protector.protect_embedding(rec["embedding"])
        t_bio = (time.perf_counter() - t0) * 1000.0
        bio_times.append(t_bio)

        # Step 4: Tracking & Kalman Filter
        t0 = time.perf_counter()
        _ = tracker.process_faces(face_records, frame=frame_bgr, embedder=embedder)
        t_track = (time.perf_counter() - t0) * 1000.0
        track_times.append(t_track)

        t_frame_end = time.perf_counter()
        e2e_times.append((t_frame_end - t_frame_start) * 1000.0)

        if (idx + 1) % 30 == 0 or idx == total_frames - 1:
            fps_so_far = (idx + 1) / (time.perf_counter() - start_total_wall)
            print(f"  -> Processed {idx + 1}/{total_frames} frames | Rolling FPS: {fps_so_far:.2f}")

    total_wall_sec = time.perf_counter() - start_total_wall
    system_fps = round(total_frames / total_wall_sec, 2)

    det_stats = calculate_stats(det_times)
    emb_stats = calculate_stats(emb_times)
    bio_stats = calculate_stats(bio_times)
    track_stats = calculate_stats(track_times)
    e2e_stats = calculate_stats(e2e_times)

    print("\n" + "=" * 75)
    print("                 BENCHMARK PERFORMANCE SUMMARY")
    print("=" * 75)
    print(f"  - Total Frames Processed:   {total_frames}")
    print(f"  - Total Elapsed Wall Time:  {total_wall_sec:.2f} s")
    print(f"  - Effective Throughput:     {system_fps} FPS")
    print("-" * 75)
    print(f"  Pipeline Stage Latency Breakdown (Mean / P95 / Max):")
    print(f"    1. SCRFD Detection:       {det_stats['mean_ms']:>6.2f} ms | P95: {det_stats['p95_ms']:>6.2f} ms | Max: {det_stats['max_ms']:>6.2f} ms")
    print(f"    2. EdgeFace INT8 Embed:   {emb_stats['mean_ms']:>6.2f} ms | P95: {emb_stats['p95_ms']:>6.2f} ms | Max: {emb_stats['max_ms']:>6.2f} ms")
    print(f"    3. Biometric Protect:     {bio_stats['mean_ms']:>6.2f} ms | P95: {bio_stats['p95_ms']:>6.2f} ms | Max: {bio_stats['max_ms']:>6.2f} ms")
    print(f"    4. Kalman & Tracking:     {track_stats['mean_ms']:>6.2f} ms | P95: {track_stats['p95_ms']:>6.2f} ms | Max: {track_stats['max_ms']:>6.2f} ms")
    print("-" * 75)
    print(f"    TOTAL END-TO-END LATENCY: {e2e_stats['mean_ms']:>6.2f} ms (P95: {e2e_stats['p95_ms']:>6.2f} ms, Max: {e2e_stats['max_ms']:>6.2f} ms)")
    print("=" * 75)

    is_realtime_capable = system_fps >= 15.0

    results = {
        "benchmark": "Speed, Latency & Stress Test (YTF)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_frames": total_frames,
        "total_duration_sec": round(total_wall_sec, 2),
        "throughput_fps": system_fps,
        "realtime_capable_ge_15fps": is_realtime_capable,
        "stages_latency_ms": {
            "scrfd_detection": det_stats,
            "edgeface_embedding": emb_stats,
            "biometric_security": bio_stats,
            "kalman_tracker": track_stats,
            "end_to_end_frame": e2e_stats,
        },
    }

    out_path = output_json or str(RESULTS_DIR / "ytf_speed_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved speed benchmark results to: {out_path}\n")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=120, help="Number of frames to benchmark")
    args = parser.parse_args()

    run_speed_stress_benchmark(num_frames=args.frames)
