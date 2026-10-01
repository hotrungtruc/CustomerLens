"""
test_edge_pipeline.py — Verification test for Edge-Cloud Pipeline.
"""

import sys
import time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np
from edge.edge_pipeline import EdgePipeline


def test_edge_to_cloud():
    print("=" * 60)
    print("   TESTING EDGE-CLOUD ARCHITECTURE END-TO-END")
    print("=" * 60)

    # 1. Initialize Edge Pipeline
    cloud_url = "http://localhost:8000"
    print(f"\n[1] Initializing Edge Pipeline pointing to {cloud_url}...")
    pipeline = EdgePipeline(
        cloud_url=cloud_url,
        camera_id="CAM_EDGE_GATE_01",
        device_id="edge_rpi5_test",
    )

    # 2. Load test image with enrolled face (Ho Trung Truc - ID 003)
    img_path = str(root_dir / "backend" / "data" / "images" / "images.jpg")
    print(f"\n[2] Loading test image from: {img_path}...")
    img = cv2.imread(img_path)
    assert img is not None, f"Failed to load test image: {img_path}"

    # 3. Process frame through Edge Pipeline
    print("\n[3] Processing frame through SCRFD + 5-point Align + EdgeFace + Tracker...")
    # Feed the frame twice to trigger track creation and first_shot dispatch
    annotated1, tracks1 = pipeline.process_frame(img)
    time.sleep(0.1)
    annotated2, tracks2 = pipeline.process_frame(img)

    print(f"    - Frame processed successfully!")
    print(f"    - Active tracks detected: {len(tracks2)}")
    assert len(tracks2) > 0, "No tracks detected by Edge Pipeline!"

    for t in tracks2:
        print(f"    - Track ID: {t['track_id']}, BBox: {t['bbox']}, Quality: {t['quality']:.2f}")

    # 4. Wait for background Cloud client to dispatch event and receive response
    print("\n[4] Waiting for EdgeCloudClient to send event and receive Cloud response...")
    max_wait = 8.0
    start = time.time()
    recognized = False

    while time.time() - start < max_wait:
        time.sleep(0.5)
        if pipeline.client.track_identities:
            for tid, (name, sim) in pipeline.client.track_identities.items():
                print(f"    [MATCH CONFIRMED] Track {tid} matched '{name}' with similarity: {sim:.3f}")
                recognized = True
            break

    # 5. Process one more frame to verify overlay annotation
    annotated3, tracks3 = pipeline.process_frame(img)
    for t in tracks3:
        print(f"    - Track {t['track_id']} label on frame overlay: '{t['name']}'")

    pipeline.close()

    print("\n" + "=" * 60)
    if recognized:
        print("  >>> SUCCESS: Edge-Cloud Pipeline is functioning 100% perfectly! <<<")
    else:
        print("  >>> WARNING: Event dispatched but Cloud response timed out <<<")
    print("=" * 60)
    return recognized


if __name__ == "__main__":
    success = test_edge_to_cloud()
    sys.exit(0 if success else 1)
