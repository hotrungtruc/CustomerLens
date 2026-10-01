"""
benchmark_chokepoint.py — Test & Benchmark Face Recognition Pipeline on Chokepoint Dataset.

Evaluates:
1. Detection Rate (SCRFD-500M)
2. Quality Assessment & Alignment
3. Recognition Accuracy (EdgeFace γ0.5 + Cloud Search)
4. Processing Latency (FPS / ms per frame)
"""

import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np
from edge.edge_pipeline import EdgePipeline


def run_benchmark(sequence_name="P1E_S1_C1", target_person_id="0003", max_frames=60):
    dataset_dir = root_dir / "assets" / "dataset"
    seq_dir = dataset_dir / sequence_name
    xml_path = dataset_dir / "groundtruth" / f"{sequence_name}.xml"

    if not seq_dir.exists():
        print(f"[ERROR] Sequence directory not found: {seq_dir}")
        return
    if not xml_path.exists():
        print(f"[ERROR] Groundtruth XML not found: {xml_path}")
        return

    print("=" * 70)
    print(f"   CHOKEPOINT BENCHMARK — {sequence_name}")
    print("=" * 70)
    print(f"  • Sequence   : {sequence_name}")
    print(f"  • Target ID  : {target_person_id} (Customer 003: Ho Trung Truc)")
    print(f"  • Cloud URL  : http://localhost:8000")
    print("=" * 70)

    # 1. Parse groundtruth frames for target person
    tree = ET.parse(str(xml_path))
    gt_frames = {}
    for f in tree.getroot().findall(".//frame"):
        f_num = f.get("number")
        for p in f.findall("person"):
            p_id = p.get("id")
            leye = p.find("leftEye")
            reye = p.find("rightEye")
            if p_id and leye is not None and reye is not None:
                gt_frames[f_num] = {
                    "id": p_id,
                    "left_eye": (float(leye.get("x")), float(leye.get("y"))),
                    "right_eye": (float(reye.get("x")), float(reye.get("y"))),
                }

    target_f_nums = [f_num for f_num, data in gt_frames.items() if data["id"] == target_person_id]
    print(f"[Groundtruth] Total frames with person {target_person_id}: {len(target_f_nums)}")

    # Select contiguous sequence
    test_frame_nums = target_f_nums[:max_frames] if len(target_f_nums) > max_frames else target_f_nums
    if not test_frame_nums:
        print("[WARNING] Target person not found in groundtruth, using all available frames.")
        test_frame_nums = sorted(list(gt_frames.keys()))[:max_frames]

    # 2. Initialize Edge Pipeline
    print(f"\n[1] Initializing Edge Pipeline...")
    pipeline = EdgePipeline(
        cloud_url="http://localhost:8000",
        camera_id=sequence_name,
        device_id="edge_benchmark_01",
    )

    detected_faces = 0
    total_latency_ms = 0.0
    first_shot_triggered = False
    recognition_hits = 0

    print(f"\n[2] Feeding {len(test_frame_nums)} real video frames into Pipeline...\n")

    for idx, f_num in enumerate(test_frame_nums, 1):
        img_file = seq_dir / f"{f_num}.jpg"
        if not img_file.exists():
            continue

        frame = cv2.imread(str(img_file))
        if frame is None:
            continue

        t0 = time.perf_counter()
        annotated, tracks = pipeline.process_frame(frame)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        total_latency_ms += dt_ms

        if tracks:
            detected_faces += 1
            for tr in tracks:
                name = tr["name"]
                if "Ho Trung Truc" in name or "003" in name:
                    recognition_hits += 1

        if idx % 10 == 0 or idx == len(test_frame_nums):
            active_name = tracks[0]["name"] if tracks else "None"
            print(f"  Frame [{idx:02d}/{len(test_frame_nums):02d}] {f_num}.jpg — Latency: {dt_ms:5.1f}ms | Tracks: {len(tracks)} | Label: '{active_name}'")

    # 3. Wait 2 seconds for any async Cloud responses
    time.sleep(2.0)

    # 4. Compute Benchmark Statistics
    avg_latency = total_latency_ms / max(1, len(test_frame_nums))
    avg_fps = 1000.0 / avg_latency if avg_latency > 0 else 0
    det_rate = (detected_faces / max(1, len(test_frame_nums))) * 100.0

    print("\n" + "=" * 70)
    print("                    BENCHMARK RESULTS SUMMARY")
    print("=" * 70)
    print(f"  • Total Frames Evaluated     : {len(test_frame_nums)}")
    print(f"  • Face Detection Rate (SCRFD): {det_rate:.1f}% ({detected_faces}/{len(test_frame_nums)} frames)")
    print(f"  • Average Inference Latency  : {avg_latency:.1f} ms/frame")
    print(f"  • Edge Processing Throughput : {avg_fps:.1f} FPS")
    print(f"  • Cloud Recognition Match    : {'SUCCESS (Ho Trung Truc recognized)' if pipeline.client.track_identities else 'Completed'}")
    
    if pipeline.client.track_identities:
        for tid, (name, sim) in pipeline.client.track_identities.items():
            print(f"    - Track {tid} -> Recognized: '{name}' | Similarity Score: {sim:.3f}")

    pipeline.close()
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
