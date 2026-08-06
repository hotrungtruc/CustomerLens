import os
import sys
import time
import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.insight_embedding import InsightEmbedder
from app.db.connection import get_db_connection
from app.db.vector_search import search_similar_faces

def compute_percentiles(latencies_ms: List[float]) -> Dict[str, float]:
    """Calculate latency metrics in milliseconds: Mean, Min, Max, P50, P90, P99."""
    if not latencies_ms:
        return {"mean": 0, "min": 0, "max": 0, "p50": 0, "p90": 0, "p99": 0}
    arr = np.array(latencies_ms)
    return {
        "mean_ms": round(float(np.mean(arr)), 2),
        "min_ms": round(float(np.min(arr)), 2),
        "max_ms": round(float(np.max(arr)), 2),
        "p50_ms": round(float(np.percentile(arr, 50)), 2),
        "p90_ms": round(float(np.percentile(arr, 90)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
    }

def benchmark_speed(num_runs: int = 200, output_json: str = None) -> Dict:
    print("=" * 70)
    print(f"  AI SPEED & LATENCY BENCHMARK")
    print(f"  Iterations: {num_runs}")
    print("=" * 70)

    embedder = InsightEmbedder()
    
    # Generate random synthetic 112x112 image
    dummy_img = np.random.randint(0, 256, (112, 112, 3), dtype=np.uint8)

    # Warmup
    print("\n[1/3] Warming up ONNX Runtime session...")
    for _ in range(10):
        _ = embedder.get_embedding(dummy_img)

    # Measure Feature Extraction Latency
    print(f"\n[2/3] Benchmarking Single Image Feature Extraction ({num_runs} runs)...")
    single_latencies = []
    
    for i in range(num_runs):
        t0 = time.perf_counter()
        _ = embedder.get_embedding(dummy_img)
        t1 = time.perf_counter()
        single_latencies.append((t1 - t0) * 1000.0)

    single_metrics = compute_percentiles(single_latencies)
    single_fps = round(1000.0 / single_metrics["mean_ms"], 2) if single_metrics["mean_ms"] > 0 else 0.0

    print(f"  [Single Image Inference]")
    print(f"    - Mean Latency : {single_metrics['mean_ms']} ms")
    print(f"    - P50 (Median) : {single_metrics['p50_ms']} ms")
    print(f"    - P90 Latency  : {single_metrics['p90_ms']} ms")
    print(f"    - P99 Latency  : {single_metrics['p99_ms']} ms")
    print(f"    - Throughput   : {single_fps} FPS (single thread)")

    # Measure Detector Latency (SCRFD)
    print("\n[3/4] Benchmarking SCRFD Face Detection on 720p Frame (1280x720)...")
    frame_720p = np.zeros((720, 1280, 3), dtype=np.uint8)
    det_latencies = []
    
    for _ in range(50):
        t0 = time.perf_counter()
        try:
            _ = embedder.detect(frame_720p)
        except Exception:
            pass
        t1 = time.perf_counter()
        det_latencies.append((t1 - t0) * 1000.0)

    det_metrics = compute_percentiles(det_latencies)
    det_fps = round(1000.0 / det_metrics["mean_ms"], 2) if det_metrics["mean_ms"] > 0 else 0.0

    print(f"  [SCRFD Detection 720p]")
    print(f"    - Mean Latency : {det_metrics['mean_ms']} ms")
    print(f"    - P50 Latency  : {det_metrics['p50_ms']} ms")
    print(f"    - P90 Latency  : {det_metrics['p90_ms']} ms")
    print(f"    - Throughput   : {det_fps} FPS")

    # Measure Vector Database Search Latency (pgvector HNSW)
    print("\n[4/4] Benchmarking Supabase pgvector HNSW Vector Search...")
    search_latencies = []
    try:
        conn = get_db_connection()
        query_vec = np.random.randn(512).astype(np.float32)
        query_vec /= np.linalg.norm(query_vec)

        # Warmup search query
        for _ in range(5):
            search_similar_faces(conn, query_vec, top_k=5, threshold=0.5)

        for _ in range(50):
            t0 = time.perf_counter()
            _ = search_similar_faces(conn, query_vec, top_k=5, threshold=0.5)
            t1 = time.perf_counter()
            search_latencies.append((t1 - t0) * 1000.0)

        conn.close()
        search_metrics = compute_percentiles(search_latencies)
        print(f"  [Supabase HNSW Search]")
        print(f"    - Mean Latency : {search_metrics['mean_ms']} ms")
        print(f"    - P50 Latency  : {search_metrics['p50_ms']} ms")
        print(f"    - P95/P99      : {search_metrics['p99_ms']} ms")
    except Exception as e:
        print(f"  [Supabase Search Warning] Database search skipped or errored: {e}")
        search_metrics = {"mean_ms": 0, "p50_ms": 0, "p90_ms": 0, "p99_ms": 0}

    results = {
        "iterations": num_runs,
        "feature_extraction_single": {
            **single_metrics,
            "fps": single_fps
        },
        "scrfd_detection_720p": {
            **det_metrics,
            "fps": det_fps
        },
        "pgvector_hnsw_search": search_metrics
    }

    if output_json:
        os.makedirs(os.path.dirname(output_json), exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nSaved Speed Benchmark results to: {output_json}")

    return results

if __name__ == "__main__":
    results_dir = os.path.join(backend_dir, "test_system", "results")
    output_path = os.path.join(results_dir, "speed_results.json")
    benchmark_speed(num_runs=200, output_json=output_path)
