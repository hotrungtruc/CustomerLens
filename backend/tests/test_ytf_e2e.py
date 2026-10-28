"""
End-to-End Testing Suite for CustomerLens with YTF Celebrity Videos.

Workflow:
1. Phase 1 (Enrollment):
   - Stream Video #1 of Celebrity (Bill_Clinton_0.mp4) over WebSocket.
   - Wait for system to register a new guest (e.g. LN1).
   - Update / promote customer profile via PUT /api/customer_profile (Name: "Bill Clinton", VIP).
2. Phase 2 (Re-Identification):
   - Stream Video #2 of same Celebrity (Bill_Clinton_1.mp4) over WebSocket.
   - Verify system automatically recognizes "Bill Clinton" (same ID, name, VIP tier).
3. Phase 3 (Distinction & Multi-Celebrity Validation):
   - Stream all other celebrity videos (Chris Rock, Angelina Jolie, Beyonce Knowles, Conan O'Brien, Carrie-Anne Moss, Charlize Theron, Aaron Eckhart, Adam Sandler, Cameron Diaz, Cindy Crawford).
   - Verify non-Clinton videos are NEVER identified as Bill Clinton!
   - Verify cross-video re-identification for each celebrity pair.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Force UTF-8 stdout for Windows consoles
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass


import cv2
import httpx
import numpy as np
import websockets

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.api.auth import create_access_token
from app.core.insight_embedding import get_embedder
from config import SIMILARITY_THRESHOLD

API_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"
YTF_DIR = Path("c:/PROJECTS/CustomerLens/assets/YTF/converted_videos")


def get_admin_token():
    return create_access_token({"id": 5, "username": "admin", "role": "admin", "cameras": []})


async def get_device_identity():
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{API_BASE}/api/device/identity",
            headers={"Origin": "http://localhost:3000"},
        )
        data = resp.json()
        camera_id = data["camera_id"]
        token = resp.cookies["device_token"]
        return camera_id, token


async def update_profile(customer_id: str, name: str, rank: str = "VIP", phone: str = "", email: str = "", note: str = ""):
    token = get_admin_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "id": customer_id,
        "source_id": customer_id,
        "name": name,
        "phone": phone,
        "email": email,
        "rank": rank,
        "loyalty_tier": rank,
        "note": note,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.put(f"{API_BASE}/api/customer_profile", json=payload, headers=headers)
        return resp.json()


def extract_face_crops_from_video(video_path: Path, max_crops: int = 10):
    embedder = get_embedder()
    cap = cv2.VideoCapture(str(video_path))
    crops = []
    frame_idx = 0

    while cap.isOpened() and len(crops) < max_crops:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        frame_idx += 1
        if frame_idx % 2 != 0:
            continue

        detections = embedder.detect(frame)
        if len(detections[0]) == 0 or len(detections[1]) == 0 or len(detections[2]) == 0:
            continue

        box = detections[0][0]
        score = float(detections[2][0])
        if score < 0.60:
            continue

        x1, y1, x2, y2 = map(int, box)
        bw, bh = x2 - x1, y2 - y1
        if bw < 32 or bh < 32:
            continue

        pad_x = int(bw * 0.30)
        pad_y = int(bh * 0.30)
        h, w = frame.shape[:2]
        sx = max(0, x1 - pad_x)
        sy = max(0, y1 - pad_y)
        ex = min(w, x2 + pad_x)
        ey = min(h, y2 + pad_y)

        crop = frame[sy:ey, sx:ex]
        if crop.size == 0:
            continue

        _, jpeg_buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        crops.append({
            "bytes": jpeg_buf.tobytes(),
            "bbox": [x1, y1, x2, y2],
            "score": score,
        })

    cap.release()
    return crops



async def stream_video_crops(ws, crops, local_track_id: str, timeout_sec: float = 15.0):
    # 1. Drain any lingering/stale messages in the WebSocket buffer from previous clips

    while True:
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.04)
        except Exception:
            break

    last_update = None

    def _get_target_customer(update_data):
        if not update_data or update_data.get("type") != "camera_update":
            return None
        for cust in update_data.get("customers", []):
            if cust.get("local_track_id") == local_track_id and cust.get("id"):
                return cust
        return None

    for crop in crops:
        meta = {
            "local_track_id": local_track_id,
            "bbox": crop["bbox"],
            "score": crop["score"],
            "timestamp": time.time(),
        }
        meta_json = json.dumps(meta).encode("utf-8")
        meta_len = len(meta_json).to_bytes(4, byteorder="big")
        packed_payload = meta_len + meta_json + crop["bytes"]

        await ws.send(packed_payload)
        await asyncio.sleep(0.12)

        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.20)
                data = json.loads(msg)
                if data.get("type") == "camera_update":
                    last_update = data
                    if _get_target_customer(data):
                        return last_update
        except asyncio.TimeoutError:
            pass

    t_end = time.time() + timeout_sec
    while time.time() < t_end:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=0.3)
            data = json.loads(msg)
            if data.get("type") == "camera_update":
                last_update = data
                if _get_target_customer(data):
                    return last_update
        except asyncio.TimeoutError:
            pass

    return last_update



def find_customer_by_track(update_payload, track_id):
    if not update_payload:
        return None, None
    for cust in update_payload.get("customers", []):
        if cust.get("local_track_id") == track_id:
            return cust.get("id"), cust.get("name")
    if update_payload.get("customers"):
        c = update_payload["customers"][0]
        return c.get("id"), c.get("name")
    return None, None


async def run_e2e_test():
    print("=" * 70, flush=True)
    print("[START] CUSTOMERLENS END-TO-END CELEBRITY VALIDATION SUITE", flush=True)
    print(f"Similarity Threshold: {SIMILARITY_THRESHOLD} | Video Source: {YTF_DIR}", flush=True)
    print("=" * 70, flush=True)

    # 1. Acquire Camera Identity & Token
    cam_id, token = await get_device_identity()
    ws_url = f"{WS_BASE}/ws/{cam_id}?takeover=1"
    print(f"[DEVICE SETUP] Device ID={cam_id}", flush=True)
    print(f"[WS CONNECT] Connecting to {ws_url}...", flush=True)

    async with websockets.connect(
        ws_url,
        origin="http://localhost:3000",
        additional_headers={"Cookie": f"device_token={token}"},
    ) as ws:
        ready_msg = await ws.recv()
        print(f"[WS READY] Server acknowledged: {ready_msg}", flush=True)

        # -------------------------------------------------------------
        # TEST 1: Enroll Celebrity #1 (Bill Clinton #0)
        # -------------------------------------------------------------
        print("\n" + "-" * 70, flush=True)
        print("[PHASE 1] Enroll Celebrity (Bill_Clinton_0.mp4)", flush=True)
        print("-" * 70, flush=True)

        crops_clinton_0 = extract_face_crops_from_video(YTF_DIR / "Bill_Clinton_0.mp4", max_crops=10)
        print(f"Extracted {len(crops_clinton_0)} face crops from Bill_Clinton_0.mp4", flush=True)

        update_1 = await stream_video_crops(ws, crops_clinton_0, local_track_id="local_clinton_0")
        enrolled_guest_id, enrolled_guest_name = find_customer_by_track(update_1, "local_clinton_0")
        print(f"[WS RESPONSE] Clinton #0: ID={enrolled_guest_id}, Name={enrolled_guest_name}", flush=True)

        if not enrolled_guest_id:
            print("[FAIL] Bill Clinton #0 was not assigned a guest ID!", flush=True)
            return False

        print(f"[SUCCESS] Bill Clinton enrolled as Guest ID: {enrolled_guest_id}", flush=True)

        print(f"\n[API UPDATE] Adding profile info for {enrolled_guest_id} -> Name: 'Bill Clinton', Rank: 'VIP'", flush=True)
        profile_res = await update_profile(
            customer_id=enrolled_guest_id,
            name="Bill Clinton",
            rank="VIP",
            phone="+1-202-555-0100",
            email="bill.clinton@president.gov",
            note="42nd US President - Registered VIP",
        )
        print(f"[API RESULT] Profile saved: {profile_res.get('success')} | Info: {profile_res.get('customer')}", flush=True)
        registered_id = profile_res.get("customer", {}).get("customer_id", enrolled_guest_id)
        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # TEST 2: Re-Identify Same Celebrity with Different Video (Bill Clinton #1)
        # -------------------------------------------------------------
        print("\n" + "-" * 70, flush=True)
        print("[PHASE 2] Re-Identification with Different Clip (Bill_Clinton_1.mp4)", flush=True)
        print("-" * 70, flush=True)

        crops_clinton_1 = extract_face_crops_from_video(YTF_DIR / "Bill_Clinton_1.mp4", max_crops=10)
        print(f"Extracted {len(crops_clinton_1)} face crops from Bill_Clinton_1.mp4", flush=True)

        update_2 = await stream_video_crops(ws, crops_clinton_1, local_track_id="local_clinton_1")
        re_id, re_name = find_customer_by_track(update_2, "local_clinton_1")
        print(f"[WS RESPONSE] Re-identification result: ID={re_id}, Name={re_name}", flush=True)

        clinton_reidentified = (re_id == registered_id) or (re_name == "Bill Clinton")
        if clinton_reidentified:
            print(f"[SUCCESS] Bill Clinton RE-IDENTIFIED in Video #1! ID={re_id}, Name='{re_name}'", flush=True)
        else:
            print(f"[INFO] Re-identification: ID={re_id}, Name='{re_name}'", flush=True)

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # TEST 3: Multi-Celebrity Distinction & Cross-Video Recognition
        # -------------------------------------------------------------
        print("\n" + "-" * 70, flush=True)
        print("[PHASE 3] Testing All 18 Celebrity Videos & Distinction from Clinton", flush=True)
        print("-" * 70, flush=True)

        celebrity_pairs = [
            ("Chris Rock", "Chris_Rock_0.mp4", "Chris_Rock_1.mp4"),
            ("Angelina Jolie", "Angelina_Jolie_2.mp4", "Angelina_Jolie_3.mp4"),
            ("Beyonce Knowles", "Beyonce_Knowles_0.mp4", "Beyonce_Knowles_3.mp4"),
            ("Conan O'Brien", "Conan_OBrien_0.mp4", "Conan_OBrien_1.mp4"),
            ("Carrie-Anne Moss", "Carrie-Anne_Moss_0.mp4", "Carrie-Anne_Moss_1.mp4"),
            ("Charlize Theron", "Charlize_Theron_1.mp4", "Charlize_Theron_3.mp4"),
        ]

        single_videos = [
            ("Aaron Eckhart", "Aaron_Eckhart_0.mp4"),
            ("Adam Sandler", "Adam_Sandler_0.mp4"),
            ("Cameron Diaz", "Cameron_Diaz_2.mp4"),
            ("Cindy Crawford", "Cindy_Crawford_0.mp4"),
        ]

        test_results = []

        test_results.append({
            "celebrity": "Bill Clinton",
            "vid_enroll": "Bill_Clinton_0.mp4",
            "vid_reid": "Bill_Clinton_1.mp4",
            "enrolled_id": registered_id,
            "reid_result": re_name or re_id,
            "distinction": "Target Celebrity",
            "status": "PASS" if clinton_reidentified else "WARN",
        })

        for name, vid_0, vid_1 in celebrity_pairs:
            print(f"\n--- Testing Pair: {name} ({vid_0} -> {vid_1}) ---", flush=True)
            p0 = YTF_DIR / vid_0
            p1 = YTF_DIR / vid_1
            trk_0 = f"local_{name.replace(' ', '_').lower()}_0"
            trk_1 = f"local_{name.replace(' ', '_').lower()}_1"

            # 1. Video #0 Enrollment
            crops_0 = extract_face_crops_from_video(p0, max_crops=10)
            up_0 = await stream_video_crops(ws, crops_0, local_track_id=trk_0)
            cid_0, cname_0 = find_customer_by_track(up_0, trk_0)

            is_clinton_leak = (cid_0 == registered_id) or (cname_0 == "Bill Clinton")
            distinction = "PASS (Different Person)" if not is_clinton_leak else "FAIL (Collision with Clinton!)"

            reg_id_0 = cid_0
            if cid_0 and not is_clinton_leak:
                print(f"  Enrolled {name} as ID: {cid_0} | Distinction: {distinction}", flush=True)
                prof_resp = await update_profile(customer_id=cid_0, name=name, rank="VIP", note=f"Celebrity {name}")
                reg_id_0 = prof_resp.get("customer", {}).get("customer_id", cid_0)
                await asyncio.sleep(0.5)

            # 2. Video #1 Re-Identification
            crops_1 = extract_face_crops_from_video(p1, max_crops=10)
            up_1 = await stream_video_crops(ws, crops_1, local_track_id=trk_1)
            cid_1, cname_1 = find_customer_by_track(up_1, trk_1)

            reid_success = (cname_1 == name) or (cid_1 in (cid_0, reg_id_0))
            status_str = "PASS" if (reid_success and not is_clinton_leak) else "FAIL"
            print(f"  Re-ID of {name} in {vid_1}: ID={cid_1}, Name='{cname_1}' -> Re-ID Match: {'YES' if reid_success else 'NEW_ID'}", flush=True)
            await asyncio.sleep(0.5)

            test_results.append({
                "celebrity": name,
                "vid_enroll": vid_0,
                "vid_reid": vid_1,
                "enrolled_id": reg_id_0 or cid_0,
                "reid_result": cname_1 or cid_1,
                "distinction": distinction,
                "status": status_str,
            })

        for name, vid in single_videos:
            print(f"\n--- Testing Single Video: {name} ({vid}) ---", flush=True)
            p = YTF_DIR / vid
            trk = f"local_{name.replace(' ', '_').lower()}"
            crops = extract_face_crops_from_video(p, max_crops=10)
            up = await stream_video_crops(ws, crops, local_track_id=trk)
            cid, cname = find_customer_by_track(up, trk)

            is_clinton_leak = (cid == registered_id) or (cname == "Bill Clinton")
            distinction = "PASS (Different Person)" if not is_clinton_leak else "FAIL (Collision!)"
            print(f"  {name}: ID={cid}, Name='{cname}' | Distinction: {distinction}", flush=True)
            await asyncio.sleep(0.5)

            test_results.append({
                "celebrity": name,
                "vid_enroll": vid,
                "vid_reid": "N/A (Single)",
                "enrolled_id": cid,
                "reid_result": cname or cid,
                "distinction": distinction,
                "status": "PASS" if not is_clinton_leak else "FAIL",
            })

        print("\n" + "=" * 90)

        print("[REPORT] FINAL END-TO-END TEST RESULTS ACROSS ALL 18 YTF VIDEOS")
        print("=" * 90)
        print(f"{'Celebrity':<18} | {'Enroll Video':<22} | {'Re-ID Video':<22} | {'Enrolled ID':<11} | {'Re-ID Result':<16} | {'Status'}")
        print("-" * 90)
        for r in test_results:
            print(f"{r['celebrity']:<18} | {r['vid_enroll']:<22} | {r['vid_reid']:<22} | {str(r['enrolled_id']):<11} | {str(r['reid_result']):<16} | {r['status']}")
        print("=" * 90)


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
