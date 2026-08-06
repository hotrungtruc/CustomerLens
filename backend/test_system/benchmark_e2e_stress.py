import os
import sys
import time
import json
import threading
import numpy as np
from pathlib import Path
from typing import Dict, List

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.insight_embedding import InsightEmbedder

def camera_stream_worker(
    embedder: InsightEmbedder, 
    duration_sec: float, 
    results_list: List[Dict], 
    worker_id: int
):
    """Simulate a single camera worker processing video frames continuously."""
    frame_720p = np.random.randint(0, 256, (720, 1280, 3), dtype=np.uint8)
    
    start_time = time.time()
    frames_processed = 0
    latencies = []

    while time.time() - start_time < duration_sec:
        t0 = time.perf_counter()
        # End-to-End single frame processing: Detect + Embed
        try:
            faces = embedder.get_faces(frame_720p)
        except Exception:
            faces = []
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)
        frames_processed += 1

    total_duration = time.time() - start_time
    fps = frames_processed / total_duration if total_duration > 0 else 0.0

    results_list.append({
        "worker_id": worker_id,
        "frames_processed": frames_processed,
        "duration_sec": round(total_duration, 2),
        "fps": round(fps, 2),
        "mean_latency_ms": round(float(np.mean(latencies)), 2) if latencies else 0.0
    })

def benchmark_e2e_stress(
    camera_counts: List[int] = [1, 2, 4], 
    test_duration_per_level: float = 5.0,
    output_json: str = None
) -> Dict:
    print("=" * 70)
    print(f"  END-TO-END MULTI-CAMERA STREAM STRESS BENCHMARK")
    print(f"  Tested Camera Concurrency Levels: {camera_counts}")
    print(f"  Duration per level: {test_duration_per_level} seconds")
    print("=" * 70)

    embedder = InsightEmbedder()
    summary = {}

    for num_cams in camera_counts:
        print(f"\n---> Testing {num_cams} Concurrent Camera Streams...")
        worker_results = []
        threads = []

        start_time = time.time()
        for i in range(num_cams):
            t = threading.Thread(
                target=camera_stream_worker,
                args=(embedder, test_duration_per_level, worker_results, i + 1)
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        total_duration = time.time() - start_time
        total_frames = sum(r["frames_processed"] for r in worker_results)
        system_fps = round(total_frames / total_duration, 2) if total_duration > 0 else 0.0
        avg_cam_fps = round(system_fps / num_cams, 2) if num_cams > 0 else 0.0

        print(f"  [Level {num_cams} Cameras Result]")
        print(f"    - Aggregate System Throughput : {system_fps} Total FPS")
        print(f"    - Average FPS per Camera Stream: {avg_cam_fps} FPS/cam")
        print(f"    - Total Frames Processed     : {total_frames} frames in {total_duration:.2f}s")

        summary[f"{num_cams}_cameras"] = {
            "num_cameras": num_cams,
            "aggregate_system_fps": system_fps,
            "avg_fps_per_camera": avg_cam_fps,
            "total_frames_processed": total_frames,
            "duration_sec": round(total_duration, 2),
            "worker_breakdown": worker_results
        }

    if output_json:
        os.makedirs(os.path.dirname(output_json), exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\nSaved E2E Stress Benchmark results to: {output_json}")

    return summary

if __name__ == "__main__":
    results_dir = os.path.join(backend_dir, "test_system", "results")
    output_path = os.path.join(results_dir, "e2e_stress_results.json")
    benchmark_e2e_stress(camera_counts=[1, 2, 4], test_duration_per_level=5.0, output_json=output_path)
