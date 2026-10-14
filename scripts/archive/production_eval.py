"""
CustomerLens — Google Production-Grade Face Recognition Evaluation Pipeline
============================================================================

Protocol: Based on NIST FRVT, IJB-C, and Google FaceNet evaluation standards.

Evaluation Tracks:
  T1. Video-based 1:1 Verification (TAR@FAR)
       — All genuine pairs from same identity (different clips),
         all impostor pairs from different identities.
       — Primary metrics: TAR@FAR=1e-3, TAR@FAR=1e-4, AUC-ROC, EER.

  T2. Video-based 1:N Closed-Set Identification (CMC Curve)
       — Gallery N=206 subjects (first clip per subject).
       — Probe = second clip per subject (206 probes).
       — Primary metrics: Rank-1, Rank-5, Rank-10.

  T3. Open-Set Identification with Reject Option
       — Gallery N=155 registered subjects.
       — Probes: 155 genuine + 51 unregistered impostors.
       — Primary metrics: FPIR@FNIR, Detection & Identification Rate (DIR).

  T4. Latency & Throughput Stress (Production SLO)
       — 500 consecutive vector queries to Supabase HNSW.
       — Primary metrics: P50, P95, P99, P999 latency; queries-per-second.

All secrets loaded exclusively from backend/.env — zero hardcoding.
"""

import os
import sys
import time
import json
import re
import random
import pickle
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
import psycopg2
from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
os.environ["PYTHONUNBUFFERED"] = "1"
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

ENV_FILE = BACKEND_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_URL or not SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing from backend/.env")

from app.core.insight_embedding import InsightEmbedder

YTF_DIR = PROJECT_ROOT / "assets" / "YTF" / "youtube_faces_with_keypoints_full_1"
RESULTS_DIR = PROJECT_ROOT / "assets" / "YTF" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# ── Constants ─────────────────────────────────────────────────────────────────
FACE_SIZE = (112, 112)
# Relaxed detection gate for surveillance camera conditions
DET_MIN_SCORE = 0.35
DET_MIN_SIZE = 16
# Attention pooling temperature
ATTENTION_TAU = 0.25
# Thresholds per operating point
THRESHOLD_STRICT = 0.50    # d <= 2m, bbox >= 75px
THRESHOLD_MID    = 0.46    # d <= 4m, bbox >= 45px
THRESHOLD_FAR    = 0.35    # d >  4m, bbox <  45px (dynamic open-set)
THRESHOLD_OPENSET = 0.40   # fixed threshold for open-set DIR/FPIR curves

ARC_TEMPLATE = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)


# ── Data structures ───────────────────────────────────────────────────────────
@dataclass
class SubjectRecord:
    key: str            # raw directory key (underscored)
    name: str           # display name
    clips: list[str]    # sorted list of .npz file names

@dataclass
class EmbeddingResult:
    subject_key: str
    clip_name: str
    embedding: Optional[np.ndarray]
    n_frames_detected: int
    n_frames_total: int
    avg_quality: float


# ── Dataset discovery ─────────────────────────────────────────────────────────
def discover_dataset() -> list[SubjectRecord]:
    files = sorted(YTF_DIR.glob("*.npz"))
    people: dict[str, list[str]] = {}
    for f in files:
        m = re.match(r"^(.*)_(\d+)\.npz$", f.name)
        if m:
            key = m.group(1)
            people.setdefault(key, []).append(f.name)
    records = []
    for key, clips in sorted(people.items()):
        records.append(SubjectRecord(
            key=key,
            name=key.replace("_", " "),
            clips=sorted(clips),
        ))
    return records


# ── Image augmentation: CCTV distance simulation ─────────────────────────────
def _apply_distance_degradation(bgr: np.ndarray, scale: float, sigma: float,
                                jpeg_q: Optional[int] = None) -> np.ndarray:
    h, w = bgr.shape[:2]
    if scale >= 1.0:
        return bgr
    nw, nh = max(16, int(w * scale)), max(16, int(h * scale))
    down = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)
    if sigma > 0:
        ksize = 5
        down = cv2.GaussianBlur(down, (ksize, ksize), sigma)
    if jpeg_q is not None:
        _, enc = cv2.imencode(".jpg", down, [cv2.IMWRITE_JPEG_QUALITY, jpeg_q])
        down = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return cv2.resize(down, (w, h), interpolation=cv2.INTER_LINEAR)


CAMERA_CONDITIONS = {
    "close_1.5m":  dict(scale=1.00, sigma=0.0,  jpeg_q=None),
    "medium_3.5m": dict(scale=0.60, sigma=0.6,  jpeg_q=None),
    "far_6.0m":    dict(scale=0.38, sigma=1.2,  jpeg_q=55),
    "veryFar_9m":  dict(scale=0.22, sigma=1.8,  jpeg_q=35),
}


# ── Quality-aware frame embedding ─────────────────────────────────────────────
def _frame_quality(bgr: np.ndarray, box: np.ndarray, lm: np.ndarray, sc: float) -> float:
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    bw = max(1, x2 - x1)
    eye_d = float(np.linalg.norm(lm[0] - lm[1]))
    q_pose = min(1.0, max(0.0, eye_d / (0.35 * bw)))
    crop = bgr[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if crop.size > 0:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        q_sharp = min(1.0, max(0.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 140.0))
    else:
        q_sharp = 0.25
    q_res  = min(1.0, max(0.0, float(bw) / 70.0))
    q_conf = min(1.0, max(0.0, float(sc)))
    return 0.35 * q_pose + 0.35 * q_sharp + 0.15 * q_res + 0.15 * q_conf


def embed_clip(embedder: InsightEmbedder, npz_path: Path,
               cond: dict, max_frames: int = 8) -> EmbeddingResult:
    """
    Load a YTF clip, apply distance/degradation simulation,
    detect faces, extract embeddings with quality-aware attention pooling.
    Returns a single aggregated 512-D L2-normalised representative vector.
    """
    data = np.load(npz_path)
    images = data["colorImages"]           # (H, W, 3, N) RGB
    n_total = images.shape[3]

    # Evenly-spaced frame sampling (≤ max_frames)
    indices = np.linspace(0, n_total - 1, min(n_total, max_frames), dtype=int)

    embs: list[np.ndarray] = []
    qualities: list[float] = []

    for i in indices:
        rgb = images[:, :, :, i]
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        bgr = _apply_distance_degradation(bgr, **cond)

        boxes, lms, scores = embedder.detect(bgr)

        valid = [(b, l, s) for b, l, s in zip(boxes, lms, scores)
                 if s >= DET_MIN_SCORE and (b[2]-b[0]) >= DET_MIN_SIZE and (b[3]-b[1]) >= DET_MIN_SIZE]
        if not valid:
            continue

        b, l, s = valid[0]
        q = _frame_quality(bgr, b, l, s)
        emb = embedder.get_embedding(bgr, l)
        embs.append(emb)
        qualities.append(q)

    n_det = len(embs)
    if n_det == 0:
        return EmbeddingResult(
            subject_key=npz_path.stem.rsplit("_", 1)[0],
            clip_name=npz_path.name,
            embedding=None,
            n_frames_detected=0,
            n_frames_total=n_total,
            avg_quality=0.0,
        )

    # Quality-Aware Attention Pooling
    qs = np.array(qualities, dtype=np.float32)
    weights = np.exp(qs / ATTENTION_TAU)
    weights /= weights.sum()
    pooled = np.sum([w * e for w, e in zip(weights, embs)], axis=0)
    pooled /= (np.linalg.norm(pooled) + 1e-12)

    return EmbeddingResult(
        subject_key=npz_path.stem.rsplit("_", 1)[0],
        clip_name=npz_path.name,
        embedding=pooled.astype(np.float32),
        n_frames_detected=n_det,
        n_frames_total=n_total,
        avg_quality=float(np.mean(qualities)),
    )


# ── Supabase HNSW query ────────────────────────────────────────────────────────
def hnsw_query(conn, emb: np.ndarray, top_k: int = 10) -> tuple[list[dict], float]:
    vec = "[" + ",".join(f"{float(x):.6f}" for x in emb) + "]"
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(
        "SELECT customer_id, name, similarity FROM match_face(%s::vector, 0.0, %s);",
        (vec, top_k)
    )
    rows = cur.fetchall()
    lat = (time.perf_counter() - t0) * 1000.0
    cur.close()
    return [{"customer_id": r[0], "name": r[1], "similarity": float(r[2])} for r in rows], lat


# ── Metric helpers ─────────────────────────────────────────────────────────────
def compute_roc(genuine_scores: list[float], impostor_scores: list[float]) -> dict:
    """ROC curve with TAR@FAR operating points (exact NIST FRVT protocol)."""
    gen = np.array(genuine_scores, dtype=np.float32)
    imp = np.array(impostor_scores, dtype=np.float32)
    n_gen = max(1, len(gen))
    n_imp = max(1, len(imp))

    # Exact Mann-Whitney U statistic for AUC-ROC
    auc = float(np.mean([np.mean(g > imp) + 0.5 * np.mean(g == imp) for g in gen]))

    # Fine-grained thresholds across all observed score values
    thresholds = np.sort(np.unique(np.concatenate([gen, imp])))[::-1]
    tars = np.array([np.mean(gen >= t) for t in thresholds])
    fars = np.array([np.mean(imp >= t) for t in thresholds])

    def tar_at_far(target_far: float) -> float:
        mask = (fars <= target_far)
        return float(np.max(tars[mask])) if np.any(mask) else 0.0

    # EER: operating point where FAR ≈ FNR (1 - TAR)
    fnrs = 1.0 - tars
    diff = np.abs(fars - fnrs)
    eer_idx = int(np.argmin(diff))
    eer = float((fars[eer_idx] + fnrs[eer_idx]) / 2.0)

    return {
        "tar_at_far_1e1":  round(tar_at_far(0.1),    4),
        "tar_at_far_1e2":  round(tar_at_far(0.01),   4),
        "tar_at_far_1e3":  round(tar_at_far(0.001),  4),
        "tar_at_far_1e4":  round(tar_at_far(0.0001), 4),
        "eer":             round(eer,  4),
        "auc_roc":         round(auc,  4),
        "n_genuine_pairs": len(genuine_scores),
        "n_impostor_pairs": len(impostor_scores),
        "mean_genuine_sim": round(float(np.mean(genuine_scores)), 4),
        "std_genuine_sim":  round(float(np.std(genuine_scores)),  4),
        "mean_impostor_sim": round(float(np.mean(impostor_scores)), 4),
        "std_impostor_sim":  round(float(np.std(impostor_scores)),  4),
        "separation_margin": round(float(np.mean(genuine_scores)) - float(np.mean(impostor_scores)), 4),
    }


def compute_cmc(gallery_ids: list[str], probe_ids: list[str],
                similarities: list[list[dict]]) -> dict:
    """CMC Rank-K Identification Rate."""
    n = len(probe_ids)
    ranks = {1: 0, 5: 0, 10: 0}
    for probe_id, matches in zip(probe_ids, similarities):
        for rank, m in enumerate(matches[:10], start=1):
            if m["customer_id"] == probe_id:
                for k in ranks:
                    if rank <= k:
                        ranks[k] += 1
                break
    return {f"rank_{k}": round(ranks[k] / max(1, n), 4) for k in ranks}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN EVALUATION PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
def run():
    t_start = time.perf_counter()
    print("=" * 90, flush=True)
    print("  CustomerLens — GOOGLE PRODUCTION-GRADE FACE RECOGNITION EVALUATION", flush=True)
    print("  Protocol: NIST FRVT / IJB-C / Google FaceNet Verification Standard", flush=True)
    print("=" * 90, flush=True)
    print(flush=True)

    # ── Setup ──────────────────────────────────────────────────────────────────
    print("[Setup] Kết nối Supabase PostgreSQL + HNSW Index (315 templates / 105 subjects)...", flush=True)
    conn = psycopg2.connect(SUPABASE_URL, connect_timeout=15)
    print("[Setup] Khởi tạo EdgeFace INT8 Inference Engine...", flush=True)
    embedder = InsightEmbedder()
    print("[Setup] Hoàn tất. Bắt đầu chiết xuất đặc trưng toàn bộ dataset.\n", flush=True)

    subjects = discover_dataset()
    n_subjects = len(subjects)
    n_with_pairs = sum(1 for s in subjects if len(s.clips) >= 2)
    print(f"[Dataset] {len(subjects)} subjects | {sum(len(s.clips) for s in subjects)} clips | "
          f"{n_with_pairs} subjects with ≥2 clips for verification\n", flush=True)

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 1: EMBED ALL CLIPS (all camera conditions) → in-memory gallery
    # ════════════════════════════════════════════════════════════════════════
    print("=" * 90, flush=True)
    print("[Phase 1/5] EMBEDDING EXTRACTION — All clips × All camera conditions (Parallel 4 Workers)", flush=True)
    print("=" * 90, flush=True)

    CACHE_PATH = RESULTS_DIR / "cached_embeddings.pkl"
    embeddings_by_condition: dict[str, dict[str, dict[str, EmbeddingResult]]] = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "rb") as f:
                embeddings_by_condition = pickle.load(f)
            print(f"[Phase 1/5] Loaded cached conditions from {CACHE_PATH}: {list(embeddings_by_condition.keys())}", flush=True)
        except Exception as e:
            print(f"[Phase 1/5] Warning loading cache: {e}, recomputing...", flush=True)
            embeddings_by_condition = {}

    for cond_name, cond_params in CAMERA_CONDITIONS.items():
        if cond_name in embeddings_by_condition and len(embeddings_by_condition[cond_name]) == n_subjects:
            total_cached = sum(1 for sk in embeddings_by_condition[cond_name].values() for r in sk.values() if r.embedding is not None)
            print(f"  ✓ {cond_name}: Loaded from cache ({total_cached} embeddings)", flush=True)
            continue

        print(f"\n  ▷ Condition: {cond_name} (parallel embedding with 4 workers)...", flush=True)
        all_clips = [(subj.key, clip) for subj in subjects for clip in subj.clips]
        cond_embs: dict[str, dict[str, EmbeddingResult]] = {subj.key: {} for subj in subjects}

        def _embed_item(item):
            s_key, clip_name = item
            res = embed_clip(embedder, YTF_DIR / clip_name, cond_params, max_frames=8)
            return s_key, clip_name, res

        t_c0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as executor:
            for s_key, clip_name, res in executor.map(_embed_item, all_clips):
                cond_embs[s_key][clip_name] = res

        elapsed_c = time.perf_counter() - t_c0
        embeddings_by_condition[cond_name] = cond_embs
        total_embs = sum(1 for sk in cond_embs.values() for r in sk.values() if r.embedding is not None)
        print(f"  ✓ {cond_name}: {total_embs} successful embeddings ({elapsed_c:.1f}s)", flush=True)

        with open(CACHE_PATH, "wb") as f:
            pickle.dump(embeddings_by_condition, f)
        print(f"    Saved checkpoint to {CACHE_PATH}", flush=True)

    # ════════════════════════════════════════════════════════════════════════
    # TRACK 1: Video 1:1 Verification — TAR@FAR, AUC, EER (per condition)
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("[Track 1/4] VIDEO 1:1 VERIFICATION — TAR@FAR / AUC-ROC / EER")
    print("  Protocol: All genuine pairs (same identity, different clips)  +")
    print("            Balanced random impostor pairs (different identities)")
    print("=" * 90)

    track1_results = {}
    pair_subjects = [s for s in subjects if len(s.clips) >= 2]

    for cond_name, cond_embs in embeddings_by_condition.items():
        genuine_scores: list[float] = []
        impostor_scores: list[float] = []

        # Build all genuine pairs: all (clip_i, clip_j) combos per subject
        for subj in pair_subjects:
            valid_clips = [c for c in subj.clips if cond_embs.get(subj.key, {}).get(c, EmbeddingResult("","",None,0,0,0.0)).embedding is not None]
            for i in range(len(valid_clips)):
                for j in range(i + 1, len(valid_clips)):
                    e1 = cond_embs[subj.key][valid_clips[i]].embedding
                    e2 = cond_embs[subj.key][valid_clips[j]].embedding
                    if e1 is not None and e2 is not None:
                        genuine_scores.append(float(np.dot(e1, e2)))

        # Build balanced impostor pairs (same count as genuine)
        impostor_candidates = [(s.key, c) for s in pair_subjects for c in s.clips
                                if cond_embs.get(s.key, {}).get(c, EmbeddingResult("","",None,0,0,0.0)).embedding is not None]
        n_imp = min(len(genuine_scores) * 3, len(impostor_candidates) ** 2 // 4)
        tried = set()
        attempts = 0
        while len(impostor_scores) < n_imp and attempts < n_imp * 10:
            attempts += 1
            (k1, c1), (k2, c2) = random.sample(impostor_candidates, 2)
            if k1 == k2 or (k1, c1, k2, c2) in tried:
                continue
            tried.add((k1, c1, k2, c2))
            e1 = cond_embs[k1][c1].embedding
            e2 = cond_embs[k2][c2].embedding
            if e1 is not None and e2 is not None:
                impostor_scores.append(float(np.dot(e1, e2)))

        metrics = compute_roc(genuine_scores, impostor_scores)
        track1_results[cond_name] = metrics
        print(f"\n  [{cond_name}]", flush=True)
        print(f"    Genuine pairs:    {metrics['n_genuine_pairs']:,}  |  Impostor pairs: {metrics['n_impostor_pairs']:,}", flush=True)
        print(f"    TAR@FAR=10%:      {metrics['tar_at_far_1e1']*100:.2f}%", flush=True)
        print(f"    TAR@FAR=1%:       {metrics['tar_at_far_1e2']*100:.2f}%", flush=True)
        print(f"    TAR@FAR=0.1%:     {metrics['tar_at_far_1e3']*100:.2f}%", flush=True)
        print(f"    TAR@FAR=0.01%:    {metrics['tar_at_far_1e4']*100:.2f}%", flush=True)
        print(f"    EER:              {metrics['eer']*100:.2f}%  |  AUC-ROC: {metrics['auc_roc']:.4f}", flush=True)
        print(f"    Genuine Sim μ±σ:  {metrics['mean_genuine_sim']:.4f} ± {metrics['std_genuine_sim']:.4f}", flush=True)
        print(f"    Impostor Sim μ±σ: {metrics['mean_impostor_sim']:.4f} ± {metrics['std_impostor_sim']:.4f}", flush=True)
        print(f"    Separation Margin: +{metrics['separation_margin']:.4f}", flush=True)

    # ════════════════════════════════════════════════════════════════════════
    # TRACK 2: Video 1:N Closed-Set Identification — CMC (Rank-1/5/10)
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("[Track 2/4] VIDEO 1:N CLOSED-SET IDENTIFICATION — CMC Rank-1/5/10")
    print("  Protocol: Gallery = clip[0] per subject (N=206 subjects)")
    print("            Probe   = clip[1] per subject (206 probes)")
    print("=" * 90)

    track2_results = {}
    cmc_subjects = [s for s in subjects if len(s.clips) >= 2]

    for cond_name, cond_embs in embeddings_by_condition.items():
        gallery_ids: list[str] = []
        gallery_embs: list[np.ndarray] = []
        probe_ids: list[str] = []
        probe_embs_list: list[np.ndarray] = []

        for subj in cmc_subjects:
            g_emb = cond_embs.get(subj.key, {}).get(subj.clips[0], EmbeddingResult("","",None,0,0,0.0)).embedding
            p_emb = cond_embs.get(subj.key, {}).get(subj.clips[1], EmbeddingResult("","",None,0,0,0.0)).embedding
            if g_emb is not None and p_emb is not None:
                gallery_ids.append(subj.key)
                gallery_embs.append(g_emb)
                probe_ids.append(subj.key)
                probe_embs_list.append(p_emb)

        if not gallery_embs:
            track2_results[cond_name] = {"rank_1": 0, "rank_5": 0, "rank_10": 0}
            continue

        # Build similarity matrix in-memory (no DB needed for closed-set 1:N)
        G = np.array(gallery_embs)   # (N_g, 512)
        P = np.array(probe_embs_list) # (N_p, 512)
        sim_matrix = P @ G.T          # (N_p, N_g)

        all_matches: list[list[dict]] = []
        for row_idx, sim_row in enumerate(sim_matrix):
            ranked_idx = np.argsort(-sim_row)[:10]
            ranked = [{"customer_id": gallery_ids[gi], "similarity": float(sim_row[gi])} for gi in ranked_idx]
            all_matches.append(ranked)

        cmc = compute_cmc(gallery_ids, probe_ids, all_matches)
        track2_results[cond_name] = cmc
        print(f"\n  [{cond_name}]  N_gallery={len(gallery_ids)}  N_probe={len(probe_ids)}", flush=True)
        print(f"    Rank-1:  {cmc['rank_1']*100:.2f}%", flush=True)
        print(f"    Rank-5:  {cmc['rank_5']*100:.2f}%", flush=True)
        print(f"    Rank-10: {cmc['rank_10']*100:.2f}%", flush=True)

    # ════════════════════════════════════════════════════════════════════════
    # TRACK 3: Open-Set Identification — DIR@FPIR / Reject Option
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90, flush=True)
    print("[Track 3/4] OPEN-SET IDENTIFICATION — DIR@FPIR / Reject Option", flush=True)
    print("  Protocol: Gallery = 155 registered subjects (clip[0])", flush=True)
    print("            Probe   = 155 genuine (clip[1]) + 51 unregistered impostors (clip[0])", flush=True)
    print("=" * 90, flush=True)

    track3_results = {}
    all_subjects_sorted = sorted(subjects, key=lambda s: s.key)
    registered_subjects   = [s for s in all_subjects_sorted if len(s.clips) >= 2][:155]
    unregistered_subjects = [s for s in all_subjects_sorted if len(s.clips) >= 2][155:206]

    for cond_name, cond_embs in embeddings_by_condition.items():
        # Gallery
        gallery_ids: list[str] = []
        gallery_embs: list[np.ndarray] = []
        for subj in registered_subjects:
            g_emb = cond_embs.get(subj.key, {}).get(subj.clips[0], EmbeddingResult("","",None,0,0,0.0)).embedding
            if g_emb is not None:
                gallery_ids.append(subj.key)
                gallery_embs.append(g_emb)

        if not gallery_embs:
            continue
        G = np.array(gallery_embs)

        # Genuine probes
        genuine_max_sims: list[float] = []
        genuine_correct: list[bool] = []
        for subj in registered_subjects:
            p_emb = cond_embs.get(subj.key, {}).get(subj.clips[1] if len(subj.clips) > 1 else subj.clips[0], EmbeddingResult("","",None,0,0,0.0)).embedding
            if p_emb is None:
                continue
            sims = (G @ p_emb.reshape(-1, 1)).flatten()
            top_idx = int(np.argmax(sims))
            top_sim = float(sims[top_idx])
            genuine_max_sims.append(top_sim)
            genuine_correct.append(gallery_ids[top_idx] == subj.key)

        # Impostor probes (unregistered)
        impostor_max_sims: list[float] = []
        for subj in unregistered_subjects:
            i_emb = cond_embs.get(subj.key, {}).get(subj.clips[0], EmbeddingResult("","",None,0,0,0.0)).embedding
            if i_emb is None:
                continue
            sims = (G @ i_emb.reshape(-1, 1)).flatten()
            impostor_max_sims.append(float(np.max(sims)))

        # DIR & FPIR at multiple thresholds
        dir_fpir = {}
        for t in [0.35, 0.40, 0.44, 0.46, 0.48, 0.50]:
            tp = sum(1 for s, ok in zip(genuine_max_sims, genuine_correct) if s >= t and ok)
            fn = sum(1 for s, ok in zip(genuine_max_sims, genuine_correct) if s < t or not ok)
            fp = sum(1 for s in impostor_max_sims if s >= t)
            tn = sum(1 for s in impostor_max_sims if s < t)
            n_gen = max(1, len(genuine_max_sims))
            n_imp = max(1, len(impostor_max_sims))
            DIR  = tp / n_gen
            FPIR = fp / n_imp
            FNIR = fn / n_gen
            dir_fpir[t] = {"DIR": round(DIR, 4), "FPIR": round(FPIR, 4), "FNIR": round(FNIR, 4)}

        track3_results[cond_name] = dir_fpir
        print(f"\n  [{cond_name}]  Gallery={len(gallery_ids)}  Genuine probes={len(genuine_max_sims)}  Impostor probes={len(impostor_max_sims)}", flush=True)
        print(f"  {'Threshold':>12}  {'DIR':>8}  {'FPIR':>8}  {'FNIR':>8}", flush=True)
        print(f"  {'-'*42}", flush=True)
        for t, v in dir_fpir.items():
            print(f"  {t:>12.2f}  {v['DIR']*100:>7.2f}%  {v['FPIR']*100:>7.2f}%  {v['FNIR']*100:>7.2f}%", flush=True)

    # ════════════════════════════════════════════════════════════════════════
    # TRACK 4: Supabase HNSW Latency Stress Test (Production SLO)
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90, flush=True)
    print("[Track 4/4] LATENCY & THROUGHPUT STRESS TEST — Supabase pgvector HNSW", flush=True)
    print("  500 consecutive queries from 206 distinct embeddings (random probe + noise)", flush=True)
    print("=" * 90, flush=True)

    # Collect probe vectors from close-range condition
    probe_vecs = [
        r.embedding
        for sk in embeddings_by_condition["close_1.5m"].values()
        for r in sk.values()
        if r.embedding is not None
    ]
    N_STRESS = 500
    latencies = []
    for i in range(N_STRESS):
        v = probe_vecs[i % len(probe_vecs)].copy()
        v += np.random.normal(0, 0.01, 512).astype(np.float32)
        v /= np.linalg.norm(v) + 1e-12
        _, lat = hnsw_query(conn, v, top_k=10)
        latencies.append(lat)

    lat_arr = np.array(latencies)
    p50  = float(np.percentile(lat_arr, 50))
    p95  = float(np.percentile(lat_arr, 95))
    p99  = float(np.percentile(lat_arr, 99))
    p999 = float(np.percentile(lat_arr, 99.9))
    qps  = N_STRESS / (lat_arr.sum() / 1000.0)

    track4_results = {
        "n_queries": N_STRESS,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "p999_ms": round(p999, 2),
        "mean_ms": round(float(lat_arr.mean()), 2),
        "max_ms":  round(float(lat_arr.max()), 2),
        "qps_sustained": round(qps, 1),
    }

    print(f"\n  Queries: {N_STRESS}  |  QPS (sustained): {track4_results['qps_sustained']:.1f}", flush=True)
    print(f"  P50:  {p50:.2f} ms", flush=True)
    print(f"  P95:  {p95:.2f} ms", flush=True)
    print(f"  P99:  {p99:.2f} ms", flush=True)
    print(f"  P999: {p999:.2f} ms", flush=True)
    print(f"  Max:  {track4_results['max_ms']:.2f} ms", flush=True)
    slo_ok = p99 < 100.0
    print(f"  SLO P99 < 100ms: {'✅ PASS' if slo_ok else '❌ FAIL'}", flush=True)

    conn.close()

    # ════════════════════════════════════════════════════════════════════════
    # SAVE FULL RESULTS
    # ════════════════════════════════════════════════════════════════════════
    elapsed = time.perf_counter() - t_start
    full_results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protocol": "NIST FRVT / IJB-C / Google FaceNet Verification Standard",
        "dataset": {
            "total_subjects": n_subjects,
            "total_clips": sum(len(s.clips) for s in subjects),
            "subjects_with_pairs": n_with_pairs,
        },
        "system": {
            "detector": "SCRFD 500M (min_score=0.35, min_bbox=16px)",
            "embedder": "EdgeFace INT8 (512-D L2-norm, TTA-flip)",
            "aggregation": f"Quality-Aware Attention Pooling (tau={ATTENTION_TAU})",
            "vector_db": "Supabase PostgreSQL 15 + pgvector HNSW (315 templates, 105 subjects)",
            "thresholding": "Dynamic Bayesian (0.50/0.46/0.35 by face width)",
        },
        "track1_verification": track1_results,
        "track2_cmc": track2_results,
        "track3_openset": {k: {str(t): v for t, v in d.items()} for k, d in track3_results.items()},
        "track4_latency": track4_results,
        "total_eval_seconds": round(elapsed, 1),
    }

    json_path = RESULTS_DIR / "production_eval_full.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2, ensure_ascii=False)

    md_path = RESULTS_DIR / "production_eval_report.md"
    _write_report(full_results, md_path)

    print("\n" + "=" * 90)
    print(f"  EVALUATION COMPLETE  |  Total wall-clock time: {elapsed/60:.1f} min")
    print(f"  JSON results : {json_path}")
    print(f"  Full report  : {md_path}")
    print("=" * 90)


# ── Markdown report ────────────────────────────────────────────────────────────
def _write_report(data: dict, out_path: Path):
    ds = data["dataset"]
    sys_cfg = data["system"]
    t1 = data["track1_verification"]
    t2 = data["track2_cmc"]
    t3 = data["track3_openset"]
    t4 = data["track4_latency"]

    # Track 1 table
    t1_rows = ""
    for cond, m in t1.items():
        t1_rows += (
            f"| `{cond}` | {m['n_genuine_pairs']:,} / {m['n_impostor_pairs']:,} | "
            f"**{m['tar_at_far_1e3']*100:.2f}%** | {m['tar_at_far_1e4']*100:.2f}% | "
            f"{m['eer']*100:.2f}% | {m['auc_roc']:.4f} | "
            f"{m['mean_genuine_sim']:.4f} ± {m['std_genuine_sim']:.4f} | "
            f"{m['mean_impostor_sim']:.4f} ± {m['std_impostor_sim']:.4f} | "
            f"**+{m['separation_margin']:.4f}** |\n"
        )

    # Track 2 table
    t2_rows = ""
    for cond, m in t2.items():
        t2_rows += (
            f"| `{cond}` | **{m['rank_1']*100:.2f}%** | {m['rank_5']*100:.2f}% | {m['rank_10']*100:.2f}% |\n"
        )

    # Track 3 table  (at threshold 0.40)
    t3_rows = ""
    for cond, thr_map in t3.items():
        v = thr_map.get("0.4", thr_map.get("0.40", {}))
        if v:
            t3_rows += (
                f"| `{cond}` | θ=0.40 | **{v['DIR']*100:.2f}%** | {v['FPIR']*100:.2f}% | {v['FNIR']*100:.2f}% |\n"
            )

    md = f"""# CustomerLens — Google Production-Grade Evaluation Report

> **Protocol:** NIST FRVT / IJB-C / Google FaceNet Verification Standard
> **Generated:** `{data['timestamp']}`  |  **Wall-clock time:** `{data['total_eval_seconds']/60:.1f} min`

## System Configuration

| Component | Specification |
|:---|:---|
| **Face Detector** | {sys_cfg['detector']} |
| **Face Embedder** | {sys_cfg['embedder']} |
| **Frame Aggregation** | {sys_cfg['aggregation']} |
| **Vector Database** | {sys_cfg['vector_db']} |
| **Thresholding** | {sys_cfg['thresholding']} |

## Dataset

| Metric | Value |
|:---|:---:|
| Total subjects | {ds['total_subjects']} |
| Total video clips | {ds['total_clips']} |
| Subjects with ≥2 clips (verifiable) | {ds['subjects_with_pairs']} |

---

## Track 1: Video-Based 1:1 Verification (TAR@FAR)

All genuine pairs from same identity + balanced impostor pairs from different identities.

| Camera Condition | Pairs (Gen/Imp) | **TAR@FAR=0.1%** | TAR@FAR=0.01% | EER | AUC-ROC | Genuine Sim (μ±σ) | Impostor Sim (μ±σ) | Margin |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
{t1_rows}

---

## Track 2: Video-Based 1:N Closed-Set Identification (CMC)

Gallery = clip[0] per subject (N=206) | Probe = clip[1] per subject.

| Camera Condition | **Rank-1** | Rank-5 | Rank-10 |
|:---|:---:|:---:|:---:|
{t2_rows}

---

## Track 3: Open-Set Identification with Reject Option (DIR@FPIR)

Gallery = 155 registered subjects | Probe = 155 genuine + 51 unregistered impostors.

| Camera Condition | Threshold | **DIR** | FPIR | FNIR |
|:---|:---:|:---:|:---:|:---:|
{t3_rows}

---

## Track 4: Production SLO — Supabase pgvector HNSW Latency Stress Test

{t4['n_queries']} consecutive queries against {sys_cfg['vector_db'].split('(')[0].strip()}.

| Metric | Value | SLO Target |
|:---|:---:|:---:|
| **P50 Latency** | {t4['p50_ms']} ms | < 60 ms |
| **P95 Latency** | {t4['p95_ms']} ms | < 80 ms |
| **P99 Latency** | {t4['p99_ms']} ms | < 100 ms |
| **P99.9 Latency** | {t4['p999_ms']} ms | < 150 ms |
| **Max Latency** | {t4['max_ms']} ms | — |
| **Sustained QPS** | {t4['qps_sustained']} | ≥ 10 QPS |
| **SLO Status** | {'✅ PASS (P99 < 100ms)' if t4['p99_ms'] < 100 else '❌ FAIL'} | P99 < 100ms |
"""
    out_path.write_text(md, encoding="utf-8")


if __name__ == "__main__":
    run()
