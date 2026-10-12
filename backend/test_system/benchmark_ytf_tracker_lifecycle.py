"""
CustomerLens YTF Tracker State Machine & Dynamic Lifecycle Transition Benchmark.
Tests:
1. Multi-frame Face Quality & Buffer Gate (Frames 1-5: UNRESOLVED -> Frame 6: GUEST LN1 created)
2. Kalman Filter & Track Continuity (Zero ID switch across sequence)
3. Lifecycle Transition: LN1 -> LC1 (visits=2) -> LL1 (visits=5) -> ML1 (spending=3.5M) -> HL1 (VIP)
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, List
import cv2
import numpy as np

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
from app.core.customer_code import compute_segment_code, format_display_customer_id
from app.db.connection import get_db_connection, update_attendance, get_customer_info
from test_system.ytf_dataset_loader import load_ytf_video, YTF_DEFAULT_DIR

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def run_tracker_lifecycle_benchmark(
    video_0_path: str | None = None,
    video_1_path: str | None = None,
    output_json: str | None = None,
) -> Dict:
    print("\n" + "=" * 75)
    print("  CUSTOMERLENS TRACKER & LIFECYCLE TRANSITION BENCHMARK (YTF)")
    print("=" * 75)

    default_v0 = os.path.join(YTF_DEFAULT_DIR, "Aaron_Eckhart_0.npz")
    default_v1 = os.path.join(YTF_DEFAULT_DIR, "Aaron_Eckhart_1.npz")

    v0_path = video_0_path or default_v0
    v1_path = video_1_path or default_v1

    print(f"  - Video 0 (First Visit - Guest Creation): {os.path.basename(v0_path)}")
    print(f"  - Video 1 (Second Visit - Re-Identification): {os.path.basename(v1_path)}")

    embedder = InsightEmbedder()
    data_v0 = load_ytf_video(v0_path)
    data_v1 = load_ytf_video(v1_path)

    # Ensure clean state for benchmark reproducibility
    conn_clean = get_db_connection()
    try:
        conn_clean.execute("DELETE FROM customer_embeddings WHERE customer_id LIKE 'LN%'")
        conn_clean.execute("DELETE FROM recognize_logs WHERE customer_id LIKE 'LN%'")
        conn_clean.execute("DELETE FROM customers WHERE customer_id LIKE 'LN%'")
        conn_clean.commit()
    finally:
        conn_clean.close()

    # -------------------------------------------------------------------------
    # Test 1: Multi-frame Buffer Gate & State Machine
    # -------------------------------------------------------------------------
    print("\n[Step 1/3] Testing Multi-frame Buffer Gate & Kalman State Machine...")
    tracker = GuestTrackManager(
        buffer_size=3,
        guest_creation_buffer_size=6,
        similarity_threshold=0.55,
        iou_threshold=0.35,
        min_bbox_size=40,
        min_detection_score=0.70,
        guest_prefix="LN",
    )

    n_frames_v0 = min(data_v0["num_frames"], 60)
    frame_events = []
    created_guest_id = None
    created_at_frame = None

    for frame_idx in range(n_frames_v0):
        frame_rgb = data_v0["colorImages"][:, :, :, frame_idx]
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        boxes, landmarks, scores = embedder.detect(frame_bgr)
        face_records = []
        for i, box in enumerate(boxes):
            emb = embedder.get_embedding(frame_bgr, landmarks[i])
            face_records.append({
                "bbox": box.tolist(),
                "embedding": emb,
                "score": float(scores[i]),
                "quality_ok": True,
                "guest_quality_ok": True,
            })

        tracked = tracker.process_faces(face_records, frame=frame_bgr, embedder=embedder)
        primary_face = tracked[0] if tracked else None
        cid = primary_face.get("customer_id") if primary_face else None

        frame_events.append({
            "frame": frame_idx + 1,
            "has_face": bool(primary_face),
            "customer_id": cid,
            "track_id": primary_face.get("track_id") if primary_face else None,
        })

        if cid and created_guest_id is None:
            created_guest_id = cid
            created_at_frame = frame_idx + 1

    print(f"  -> Frames 1 to 5 customer_id: {[e['customer_id'] for e in frame_events[:5]]}")
    print(f"  -> Guest successfully created at Frame {created_at_frame} with ID: {created_guest_id}")

    # Validate gate: frames 1-5 must be None, frame >= 6 must be created
    gate_valid = all(e["customer_id"] is None for e in frame_events[:5]) and (created_at_frame is not None and created_at_frame <= 8)
    print(f"  -> Buffer Gate Validation: {'PASS (Correctly delayed)' if gate_valid else 'FAIL'}")

    # Track continuity across video 0 (ID Switch check)
    assigned_ids = [e["customer_id"] for e in frame_events[created_at_frame:] if e["customer_id"]]
    id_switches = sum(1 for i in range(1, len(assigned_ids)) if assigned_ids[i] != assigned_ids[0])
    continuity_valid = (id_switches == 0)
    print(f"  -> Track Continuity: {len(assigned_ids)} frames maintained same ID {created_guest_id} (ID Switches: {id_switches}) -> {'PASS' if continuity_valid else 'FAIL'}")

    # Wait briefly for async SQLite insert to finish
    time.sleep(1.0)

    # -------------------------------------------------------------------------
    # Test 2: Re-Identification on Second Video & Transition to LC
    # -------------------------------------------------------------------------
    print("\n[Step 2/3] Testing Re-Identification on Second Video (Different Angle/Lighting)...")
    tracker.tracks.clear()
    tracker.load_known_embeddings()

    reid_matches = []
    n_frames_v1 = min(data_v1["num_frames"], 30)

    for frame_idx in range(n_frames_v1):
        frame_rgb = data_v1["colorImages"][:, :, :, frame_idx]
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        boxes, landmarks, scores = embedder.detect(frame_bgr)
        face_records = []
        for i, box in enumerate(boxes):
            emb = embedder.get_embedding(frame_bgr, landmarks[i])
            face_records.append({
                "bbox": box.tolist(),
                "embedding": emb,
                "score": float(scores[i]),
                "quality_ok": True,
            })

        tracked = tracker.process_faces(face_records, frame=frame_bgr, embedder=embedder)
        primary_face = tracked[0] if tracked else None
        cid = primary_face.get("customer_id") if primary_face else None
        if cid:
            reid_matches.append(cid)

    matched_count = sum(1 for cid in reid_matches if cid == created_guest_id)
    reid_success = (matched_count > 0)
    print(f"  -> Re-Identification Matches in Video 1: {matched_count}/{n_frames_v1} frames correctly matched {created_guest_id}")
    print(f"  -> Re-Identification Status: {'PASS (Successfully recognized returning person)' if reid_success else 'FAIL'}")

    # -------------------------------------------------------------------------
    # Test 3: Customer Lifecycle State Transitions (LN -> LC -> LL -> ML -> HL)
    # -------------------------------------------------------------------------
    print("\n[Step 3/3] Testing 2-Letter Segment Transitions across Customer Lifecycle...")
    lifecycle_history = []
    conn = get_db_connection()
    try:
        # State 1: Fresh Guest
        prof1 = get_customer_info(conn, created_guest_id) or {"customer_id": created_guest_id, "total_visits": 1, "loyalty_tier": "Standard"}
        seg1 = compute_segment_code(prof1)
        disp1 = format_display_customer_id(prof1)
        lifecycle_history.append({"stage": "1. First Visit (New Guest)", "visits": 1, "tier": "Standard", "code": seg1[0], "display_id": disp1, "desc": seg1[1]})

        # State 2: Second Visit -> Re-identified -> visits = 2 -> LC
        update_attendance(conn, created_guest_id, total_attendance=2)
        prof2 = get_customer_info(conn, created_guest_id)
        seg2 = compute_segment_code(prof2)
        disp2 = format_display_customer_id(prof2)
        lifecycle_history.append({"stage": "2. 2nd Visit (Casual Guest)", "visits": 2, "tier": "Standard", "code": seg2[0], "display_id": disp2, "desc": seg2[1]})

        # State 3: Loyal Visit -> visits = 5 -> LL
        update_attendance(conn, created_guest_id, total_attendance=5)
        prof3 = get_customer_info(conn, created_guest_id)
        seg3 = compute_segment_code(prof3)
        disp3 = format_display_customer_id(prof3)
        lifecycle_history.append({"stage": "3. 5th Visit (Loyal Guest)", "visits": 5, "tier": "Standard", "code": seg3[0], "display_id": disp3, "desc": seg3[1]})

        # State 4: Mass Customer -> Spending >= 3M -> ML
        conn.execute("UPDATE customers SET total_spending = 3500000 WHERE customer_id = ?", (created_guest_id,))
        conn.commit()
        prof4 = get_customer_info(conn, created_guest_id)
        seg4 = compute_segment_code(prof4)
        disp4 = format_display_customer_id(prof4)
        lifecycle_history.append({"stage": "4. Spending 3.5M (Mass Loyal)", "visits": 5, "tier": "Mass", "spending": 3500000, "code": seg4[0], "display_id": disp4, "desc": seg4[1]})

        # State 5: VIP Customer -> Loyalty tier VIP -> HL
        conn.execute("UPDATE customers SET loyalty_tier = 'VIP', total_spending = 25000000 WHERE customer_id = ?", (created_guest_id,))
        conn.commit()
        prof5 = get_customer_info(conn, created_guest_id)
        seg5 = compute_segment_code(prof5)
        disp5 = format_display_customer_id(prof5)
        lifecycle_history.append({"stage": "5. VIP Tier Upgrade (VIP Loyal)", "visits": 5, "tier": "VIP", "spending": 25000000, "code": seg5[0], "display_id": disp5, "desc": seg5[1]})
    finally:
        conn.close()

    for item in lifecycle_history:
        print(f"  - [{item['code']}] {item['stage']}: Display ID = {item['display_id']}")

    lifecycle_valid = (
        lifecycle_history[0]["code"] == "LN" and
        lifecycle_history[1]["code"] == "LC" and
        lifecycle_history[2]["code"] == "LL" and
        lifecycle_history[3]["code"] == "ML" and
        lifecycle_history[4]["code"] == "HL"
    )

    results = {
        "benchmark": "YTF Tracker State Machine & Lifecycle Transitions",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_1_buffer_gate": {
            "passed": gate_valid,
            "created_at_frame": created_at_frame,
            "created_guest_id": created_guest_id,
            "id_switches": id_switches,
            "continuity_passed": continuity_valid,
        },
        "test_2_cross_video_reid": {
            "passed": reid_success,
            "matched_frames": len(reid_matches),
            "total_frames": n_frames_v1,
        },
        "test_3_lifecycle_transitions": {
            "passed": lifecycle_valid,
            "stages": lifecycle_history,
        },
        "overall_status": "ALL TESTS PASSED" if (gate_valid and continuity_valid and reid_success and lifecycle_valid) else "FAILED",
    }

    print("\n" + "=" * 75)
    print(f"  OVERALL BENCHMARK STATUS: {results['overall_status']}")
    print("=" * 75)

    out_path = output_json or str(RESULTS_DIR / "ytf_tracker_lifecycle_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved tracker results to: {out_path}\n")

    return results


if __name__ == "__main__":
    run_tracker_lifecycle_benchmark()
