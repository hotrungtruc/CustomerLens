"""
scripts/e2e_production_test.py
=============================================================================
End-to-End System Evaluation on YTF (YouTube Faces) Dataset
Validates full pipeline:
  1. Enrollment (Đăng ký định danh) into live Supabase PostgreSQL (pgvector).
     - Measures end-to-end registration latency.
  2. Re-Identification (Nhận diện lại khách cũ) from different video clips.
     - Measures recognition latency and Rank-1 accuracy against live DB.
  3. New Guest Isolation (Kiểm tra khách mới).
     - Feeds unseen subjects to verify zero false matches against existing customers.
=============================================================================
"""

import os
import sys
import time
import json
from pathlib import Path
from collections import defaultdict
import cv2
import numpy as np

# Set environment
os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["USE_SUPABASE"] = "true"
os.environ["DB_TYPE"] = "postgresql"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db.pool import get_db_connection
from app.db.repositories.customers import upsert_customer
from app.db.vector_search import insert_embedding_with_vector, search_similar_faces
from app.core.insight_embedding import InsightEmbedder

YTF_DIR = PROJECT_ROOT / "assets" / "YTF" / "youtube_faces_with_keypoints_full_1"
RESULTS_DIR = PROJECT_ROOT / "assets" / "YTF" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_THRESHOLD = 0.55  # Production recognition threshold


def load_clip_representative_embedding(embedder: InsightEmbedder, npz_path: Path, max_frames: int = 8):
    """Load frames from YTF .npz, detect faces via SCRFD, extract and aggregate embeddings."""
    data = np.load(npz_path)
    images = data["colorImages"]  # (H, W, 3, N) RGB
    n_total = images.shape[3]
    if n_total == 0:
        return None

    indices = np.linspace(0, n_total - 1, min(n_total, max_frames), dtype=int)
    embs = []

    for idx in indices:
        rgb = images[:, :, :, idx]
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        boxes, landmarks, scores = embedder.detect(bgr)
        valid = [
            (b, l, s) for b, l, s in zip(boxes, landmarks, scores)
            if s >= 0.35 and (b[2] - b[0]) >= 20 and (b[3] - b[1]) >= 20
        ]
        if valid:
            best_b, best_lm, best_sc = max(valid, key=lambda x: x[2])
            emb = embedder.get_embedding(bgr, best_lm)
            if emb is not None:
                embs.append(emb)

    if not embs:
        return None

    # Mean embedding & normalize
    mean_emb = np.mean(embs, axis=0)
    norm = np.linalg.norm(mean_emb)
    if norm > 0:
        mean_emb = mean_emb / norm
    return mean_emb.astype(np.float32)


def run_e2e_test(num_gallery: int = 30, num_new_guests: int = 20):
    print("=" * 80)
    print("CUSTOMERLENS END-TO-END PRODUCTION SYSTEM EVALUATION")
    print("=" * 80)
    print(f"Dataset path: {YTF_DIR}")
    print(f"System recognition threshold: {SYSTEM_THRESHOLD}")
    print(f"Config: {num_gallery} Gallery Subjects (Enrolled) + {num_new_guests} Unseen Subjects (New Guests)")
    print("-" * 80)

    # 1. Discover subjects with clips
    print("[1/5] Scanning dataset subjects...")
    all_files = list(YTF_DIR.glob("*.npz"))
    subject_map = defaultdict(list)
    for f in all_files:
        name = f.stem.rsplit("_", 1)[0]
        subject_map[name].append(f)

    # Eligible for gallery: >= 2 clips
    eligible_gallery = [k for k, v in subject_map.items() if len(v) >= 2]
    eligible_gallery.sort()

    if len(eligible_gallery) < num_gallery:
        raise RuntimeError(f"Not enough gallery subjects: found {len(eligible_gallery)}, needed {num_gallery}")

    selected_gallery = eligible_gallery[:num_gallery]
    remaining = [k for k in subject_map.keys() if k not in selected_gallery]
    remaining.sort()
    selected_new_guests = remaining[:num_new_guests]

    print(f"  Selected {len(selected_gallery)} gallery subjects (2 clips each: 1 enroll, 1 probe)")
    print(f"  Selected {len(selected_new_guests)} unseen subjects as new guests")

    # 2. Initialize Models & Database
    print("\n[2/5] Initializing InsightEmbedder and Supabase connection...")
    embedder = InsightEmbedder()
    conn = get_db_connection()

    # Clean existing E2E records
    print("  Cleaning previous E2E test records from Supabase...")
    conn.execute("DELETE FROM customer_embeddings WHERE customer_id LIKE 'E2E_%';")
    conn.execute("DELETE FROM customers WHERE customer_id LIKE 'E2E_%';")
    conn.commit()
    print("  Database ready.")

    # 3. Phase 1: Enrollment (Đăng ký định danh)
    print(f"\n[3/5] ENROLLMENT PHASE ({num_gallery} subjects)...")
    print("-" * 80)
    print(f"{'ID':<10} | {'Subject Name':<28} | {'Clip':<20} | {'Latency (ms)':<12} | {'Status'}")
    print("-" * 80)

    enrollment_results = []
    gallery_info = {}

    for idx, subj in enumerate(selected_gallery, 1):
        cid = f"E2E_CUST_{idx:03d}"
        clips = sorted(subject_map[subj], key=lambda x: x.name)
        enroll_clip = clips[0]

        # Extract embedding
        emb = load_clip_representative_embedding(embedder, enroll_clip)
        if emb is None:
            print(f"{cid:<10} | {subj:<28} | {enroll_clip.name:<20} | {'FAILED':<12} | Face detection failed")
            continue

        # Measure DB Enrollment Latency
        t0 = time.perf_counter()
        blob = emb.tobytes()
        formatted_name = subj.replace("_", " ")

        upsert_customer(
            conn,
            customer_id=cid,
            name=formatted_name,
            customer_type="registered",
            service_category="VIP",
        )
        insert_embedding_with_vector(
            conn,
            customer_id=cid,
            face_embedding_blob=blob,
            embedding_np=emb,
            dim=512,
            model_name="edgeface_int8",
        )
        conn.commit()
        t_enroll = (time.perf_counter() - t0) * 1000.0  # ms

        enrollment_results.append({
            "customer_id": cid,
            "subject": subj,
            "name": formatted_name,
            "enroll_clip": enroll_clip.name,
            "latency_ms": t_enroll,
            "probe_clip": clips[1].name,
            "probe_path": str(clips[1]),
        })
        gallery_info[cid] = subj

        print(f"{cid:<10} | {formatted_name:<28} | {enroll_clip.name:<20} | {t_enroll:8.2f} ms | SUCCESS")

    # 4. Phase 2: Re-Identification (Nhận diện lại khách cũ bằng video khác)
    print(f"\n[4/5] RE-IDENTIFICATION PHASE ({len(enrollment_results)} probes)...")
    print("-" * 80)
    print(f"{'Probe Subject':<25} | {'Expected ID':<12} | {'Matched ID':<12} | {'Sim':<6} | {'Lat (ms)':<9} | {'Result'}")
    print("-" * 80)

    reid_results = []
    for item in enrollment_results:
        cid = item["customer_id"]
        subj = item["subject"]
        probe_path = Path(item["probe_path"])

        probe_emb = load_clip_representative_embedding(embedder, probe_path)
        if probe_emb is None:
            continue

        # Measure Re-identification Query Latency
        t0 = time.perf_counter()
        results = search_similar_faces(conn, probe_emb, top_k=3, threshold=0.0)
        t_query = (time.perf_counter() - t0) * 1000.0  # ms

        top_match_id = results[0][0] if results else None
        top_sim = float(results[0][1]) if results else 0.0

        is_rank1 = (top_match_id == cid)
        is_accepted = is_rank1 and (top_sim >= SYSTEM_THRESHOLD)

        status_str = "MATCH (VERIFIED)" if is_accepted else ("MATCH (LOW CONF)" if is_rank1 else "MISMATCH")

        reid_results.append({
            "subject": subj,
            "expected_id": cid,
            "matched_id": top_match_id,
            "similarity": top_sim,
            "latency_ms": t_query,
            "rank1_correct": is_rank1,
            "accepted_threshold": is_accepted,
        })

        print(f"{subj:<25} | {cid:<12} | {str(top_match_id):<12} | {top_sim:5.3f} | {t_query:7.2f} ms | {status_str}")

    # 5. Phase 3: New Guest Testing (Khách mới - Kiểm tra nhầm lẫn)
    print(f"\n[5/5] NEW GUEST / UNSEEN SUBJECT ISOLATION PHASE ({len(selected_new_guests)} guests)...")
    print("-" * 80)
    print(f"{'New Guest Subject':<28} | {'Best Gallery Match':<18} | {'Max Sim':<8} | {'Lat (ms)':<9} | {'System Decision'}")
    print("-" * 80)

    new_guest_results = []
    for idx, subj in enumerate(selected_new_guests, 1):
        clips = sorted(subject_map[subj], key=lambda x: x.name)
        guest_clip = clips[0]

        guest_emb = load_clip_representative_embedding(embedder, guest_clip)
        if guest_emb is None:
            continue

        t0 = time.perf_counter()
        results = search_similar_faces(conn, guest_emb, top_k=3, threshold=0.0)
        t_query = (time.perf_counter() - t0) * 1000.0  # ms

        # Find best match that belongs to our enrolled gallery
        gallery_matches = [r for r in results if r[0] in gallery_info]
        best_id = gallery_matches[0][0] if gallery_matches else (results[0][0] if results else None)
        max_sim = float(gallery_matches[0][1]) if gallery_matches else (float(results[0][1]) if results else 0.0)

        # A false match occurs if similarity >= SYSTEM_THRESHOLD
        is_false_match = (max_sim >= SYSTEM_THRESHOLD)
        decision_str = "FALSE MATCH (ERROR)" if is_false_match else "NEW GUEST (CORRECT REJECT)"

        new_guest_results.append({
            "guest_subject": subj,
            "best_gallery_match": best_id,
            "max_similarity": max_sim,
            "latency_ms": t_query,
            "is_false_match": is_false_match,
            "is_correct_reject": not is_false_match,
        })

        print(f"{subj:<28} | {str(best_id):<18} | {max_sim:7.3f} | {t_query:7.2f} ms | {decision_str}")

    # Clean up test records
    print("\n[Cleaning up E2E test records from Supabase...]")
    conn.execute("DELETE FROM customer_embeddings WHERE customer_id LIKE 'E2E_%';")
    conn.execute("DELETE FROM customers WHERE customer_id LIKE 'E2E_%';")
    conn.commit()
    conn.close()

    # 6. Aggregate Statistics
    enroll_times = [r["latency_ms"] for r in enrollment_results]
    reid_times = [r["latency_ms"] for r in reid_results]
    new_guest_times = [r["latency_ms"] for r in new_guest_results]

    rank1_count = sum(1 for r in reid_results if r["rank1_correct"])
    verified_count = sum(1 for r in reid_results if r["accepted_threshold"])
    genuine_sims = [r["similarity"] for r in reid_results]

    false_match_count = sum(1 for r in new_guest_results if r["is_false_match"])
    correct_reject_count = sum(1 for r in new_guest_results if r["is_correct_reject"])
    impostor_sims = [r["max_similarity"] for r in new_guest_results]

    print("\n" + "=" * 80)
    print("📊 BẢNG TỔNG HỢP KẾT QUẢ ĐÁNH GIÁ HỆ THỐNG TOÀN DIỆN (END-TO-END)")
    print("=" * 80)
    print("1. HIỆU NĂNG THỜI GIAN (LATENCY BENCHMARK):")
    print(f"  • Thời gian Đăng ký định danh (Enrollment Latency):")
    print(f"      - Trung bình (Mean) : {np.mean(enroll_times):.2f} ms")
    print(f"      - Median (P50)      : {np.median(enroll_times):.2f} ms")
    print(f"      - P95               : {np.percentile(enroll_times, 95):.2f} ms")
    print(f"      - Nhanh nhất (Min)  : {np.min(enroll_times):.2f} ms")
    print(f"      - Chậm nhất (Max)   : {np.max(enroll_times):.2f} ms")
    print(f"  • Thời gian Nhận diện lại (Re-identification Query Latency):")
    print(f"      - Trung bình (Mean) : {np.mean(reid_times):.2f} ms")
    print(f"      - Median (P50)      : {np.median(reid_times):.2f} ms")
    print(f"      - P95               : {np.percentile(reid_times, 95):.2f} ms")
    print(f"      - Nhanh nhất (Min)  : {np.min(reid_times):.2f} ms")
    print(f"      - Chậm nhất (Max)   : {np.max(reid_times):.2f} ms")

    print("\n2. ĐỘ CHÍNH XÁC NHẬN DIỆN LẠI KHÁCH CŨ (RE-IDENTIFICATION ACCURACY):")
    print(f"  • Tổng số lượt test nhận diện lại (Probes) : {len(reid_results)}")
    print(f"  • Rank-1 Identification Accuracy           : {rank1_count}/{len(reid_results)} ({rank1_count/len(reid_results)*100:.1f}%)")
    print(f"  • True Accept Rate (TAR @ Sim >= {SYSTEM_THRESHOLD})  : {verified_count}/{len(reid_results)} ({verified_count/len(reid_results)*100:.1f}%)")
    print(f"  • Điểm tương đồng Genuine trung bình       : {np.mean(genuine_sims):.4f} (Max: {np.max(genuine_sims):.4f}, Min: {np.min(genuine_sims):.4f})")

    print("\n3. ĐỘ AN TOÀN VÀ PHÂN BIỆT KHÁCH MỚI (NEW GUEST ISOLATION & ZERO CONFUSION):")
    print(f"  • Tổng số khách mới chưa từng đăng ký      : {len(new_guest_results)}")
    print(f"  • Số ca bị nhận nhầm thành khách cũ (FAR)  : {false_match_count}/{len(new_guest_results)} ({false_match_count/len(new_guest_results)*100:.1f}%)")
    print(f"  • Phân loại chuẩn xác là Khách Mới (TRR)   : {correct_reject_count}/{len(new_guest_results)} ({correct_reject_count/len(new_guest_results)*100:.1f}%)")
    print(f"  • Điểm tương đồng Impostor lớn nhất (Max)  : {np.max(impostor_sims):.4f} (Ngưỡng hệ thống: {SYSTEM_THRESHOLD})")
    print(f"  • Khoảng cách an toàn (Safety Margin)      : {np.mean(genuine_sims) - np.max(impostor_sims):.4f}")
    print("=" * 80)

    # Save to JSON
    summary_data = {
        "num_gallery": num_gallery,
        "num_new_guests": num_new_guests,
        "system_threshold": SYSTEM_THRESHOLD,
        "enrollment_latency_ms": {
            "mean": float(np.mean(enroll_times)),
            "p50": float(np.median(enroll_times)),
            "p95": float(np.percentile(enroll_times, 95)),
            "min": float(np.min(enroll_times)),
            "max": float(np.max(enroll_times)),
        },
        "reid_latency_ms": {
            "mean": float(np.mean(reid_times)),
            "p50": float(np.median(reid_times)),
            "p95": float(np.percentile(reid_times, 95)),
            "min": float(np.min(reid_times)),
            "max": float(np.max(reid_times)),
        },
        "reid_accuracy": {
            "total_probes": len(reid_results),
            "rank1_correct": rank1_count,
            "rank1_accuracy_percent": float(rank1_count / len(reid_results) * 100),
            "tar_percent": float(verified_count / len(reid_results) * 100),
            "mean_genuine_similarity": float(np.mean(genuine_sims)),
            "min_genuine_similarity": float(np.min(genuine_sims)),
            "max_genuine_similarity": float(np.max(genuine_sims)),
        },
        "new_guest_isolation": {
            "total_unseen_guests": len(new_guest_results),
            "false_accept_count": false_match_count,
            "false_accept_rate_percent": float(false_match_count / len(new_guest_results) * 100),
            "true_reject_count": correct_reject_count,
            "true_reject_rate_percent": float(correct_reject_count / len(new_guest_results) * 100),
            "max_impostor_similarity": float(np.max(impostor_sims)),
            "mean_impostor_similarity": float(np.mean(impostor_sims)),
            "safety_margin": float(np.mean(genuine_sims) - np.max(impostor_sims)),
        },
        "enrollment_details": enrollment_results,
        "reid_details": reid_results,
        "new_guest_details": new_guest_results,
    }

    out_file = RESULTS_DIR / "e2e_production_test_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
    print(f"\nSaved detailed JSON results to: {out_file}")


if __name__ == "__main__":
    run_e2e_test(num_gallery=30, num_new_guests=20)
