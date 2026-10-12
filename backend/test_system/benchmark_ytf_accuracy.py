"""
CustomerLens YTF Biometrics Accuracy Benchmark.
Evaluates 1:1 Cross-Video Face Verification and 1:N Identification
using the YouTube Faces Dataset (YTF).
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Tuple
import cv2
import numpy as np

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.insight_embedding import InsightEmbedder
from app.core.tracking.embedding_utils import normalize_embedding, calculate_robust_mean_embedding
from test_system.ytf_dataset_loader import (
    load_ytf_video,
    get_ytf_verification_pairs,
    get_ytf_gallery_probe_split,
    YTF_DEFAULT_DIR,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def extract_video_embedding(embedder: InsightEmbedder, npz_path: str, max_frames: int = 5) -> np.ndarray | None:
    """
    Extracts a robust mean embedding across the first max_frames quality frames of a YTF video.
    """
    try:
        data = load_ytf_video(npz_path)
        color_images = data["colorImages"]  # (H, W, 3, N)
        n_frames = min(color_images.shape[-1], max_frames * 3)

        frame_embeddings = []
        for i in range(n_frames):
            frame_rgb = color_images[:, :, :, i]
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

            boxes, landmarks, scores = embedder.detect(frame_bgr)
            if len(boxes) > 0 and len(landmarks) > 0:
                # Find best face
                best_idx = int(np.argmax(scores))
                if scores[best_idx] >= 0.6:
                    emb = embedder.get_embedding(frame_bgr, landmarks[best_idx])
                    if emb is not None:
                        frame_embeddings.append(normalize_embedding(emb))
                        if len(frame_embeddings) >= max_frames:
                            break

        if not frame_embeddings:
            # Fallback to frame 0 with minimal score check
            frame_bgr = cv2.cvtColor(color_images[:, :, :, 0], cv2.COLOR_RGB2BGR)
            boxes, landmarks, _ = embedder.detect(frame_bgr)
            if len(landmarks) > 0:
                emb = embedder.get_embedding(frame_bgr, landmarks[0])
                if emb is not None:
                    return normalize_embedding(emb)
            return None

        return calculate_robust_mean_embedding(frame_embeddings)
    except Exception as e:
        print(f"[Warning] Failed to extract embedding for {npz_path}: {e}")
        return None


def run_ytf_accuracy_benchmark(
    dataset_dir: str = YTF_DEFAULT_DIR,
    max_identities: int = 100,
    num_impostors_per_id: int = 3,
    output_json: str | None = None,
) -> Dict:
    print("\n" + "=" * 75)
    print("  CUSTOMERLENS BIOMETRICS ACCURACY BENCHMARK ON YOUTUBE FACES (YTF)")
    print(f"  Identities: {max_identities} | Dataset: {dataset_dir}")
    print("=" * 75)

    embedder = InsightEmbedder()

    # 1. Generate Pairs & Splits
    print("\n[Step 1/4] Generating Cross-Video Genuine and Impostor Pairs...")
    gen_pairs, imp_pairs, id_map = get_ytf_verification_pairs(
        dataset_dir=dataset_dir,
        max_identities=max_identities,
        num_impostors_per_id=num_impostors_per_id,
        seed=42,
    )
    gallery_dict, probe_list = get_ytf_gallery_probe_split(id_map)
    print(f"  -> Sampled {len(id_map)} identities.")
    print(f"  -> Generated {len(gen_pairs)} Genuine Pairs (same person, different videos).")
    print(f"  -> Generated {len(imp_pairs)} Impostor Pairs (different persons).")
    print(f"  -> 1:N Gallery: {len(gallery_dict)} identities, Probes: {len(probe_list)} videos.")

    # 2. Extract Embeddings (with cache to avoid recomputing same video)
    print("\n[Step 2/4] Extracting EdgeFace Embeddings across Video Sequences...")
    unique_videos = set()
    for v1, v2, _ in gen_pairs:
        unique_videos.add(v1)
        unique_videos.add(v2)
    for v1, v2, _, _ in imp_pairs:
        unique_videos.add(v1)
        unique_videos.add(v2)

    video_embeddings: Dict[str, np.ndarray] = {}
    start_ext = time.time()
    for idx, vid_path in enumerate(sorted(unique_videos), 1):
        emb = extract_video_embedding(embedder, vid_path)
        if emb is not None:
            video_embeddings[vid_path] = emb
        if idx % 50 == 0 or idx == len(unique_videos):
            print(f"  -> Extracted {idx}/{len(unique_videos)} videos ({time.time() - start_ext:.1f}s)...")

    # 3. 1:1 Verification Evaluation
    print("\n[Step 3/4] Computing 1:1 Cross-Video Verification Metrics...")
    gen_sims = []
    for v1, v2, _ in gen_pairs:
        if v1 in video_embeddings and v2 in video_embeddings:
            sim = float(np.dot(video_embeddings[v1], video_embeddings[v2]))
            gen_sims.append(sim)

    imp_sims = []
    for v1, v2, _, _ in imp_pairs:
        if v1 in video_embeddings and v2 in video_embeddings:
            sim = float(np.dot(video_embeddings[v1], video_embeddings[v2]))
            imp_sims.append(sim)

    gen_sims = np.array(gen_sims, dtype=np.float32)
    imp_sims = np.array(imp_sims, dtype=np.float32)

    # Threshold analysis
    thresholds = np.linspace(0.0, 1.0, 1001)
    far_list, frr_list, tar_list = [], [], []

    for t in thresholds:
        far = float(np.mean(imp_sims >= t))  # False Acceptance Rate
        frr = float(np.mean(gen_sims < t))   # False Rejection Rate
        tar = 1.0 - frr                      # True Acceptance Rate
        far_list.append(far)
        frr_list.append(frr)
        tar_list.append(tar)

    far_arr = np.array(far_list)
    frr_arr = np.array(frr_list)
    tar_arr = np.array(tar_list)

    # EER calculation
    eer_idx = int(np.argmin(np.abs(far_arr - frr_arr)))
    eer = float((far_arr[eer_idx] + frr_arr[eer_idx]) / 2.0)
    eer_threshold = float(thresholds[eer_idx])

    # TAR @ specific FAR
    def get_tar_at_far(target_far: float) -> Tuple[float, float]:
        idx = int(np.argmin(np.abs(far_arr - target_far)))
        return float(tar_arr[idx]), float(thresholds[idx])

    tar_at_far_1pct, thresh_1pct = get_tar_at_far(0.01)
    tar_at_far_01pct, thresh_01pct = get_tar_at_far(0.001)

    # System threshold evaluation (0.55)
    sys_thresh = 0.55
    sys_tp = int(np.sum(gen_sims >= sys_thresh))
    sys_fn = int(np.sum(gen_sims < sys_thresh))
    sys_fp = int(np.sum(imp_sims >= sys_thresh))
    sys_tn = int(np.sum(imp_sims < sys_thresh))

    sys_accuracy = (sys_tp + sys_tn) / (len(gen_sims) + len(imp_sims))
    sys_precision = sys_tp / (sys_tp + sys_fp) if (sys_tp + sys_fp) > 0 else 0.0
    sys_recall = sys_tp / (sys_tp + sys_fn) if (sys_tp + sys_fn) > 0 else 0.0
    sys_f1 = (2 * sys_precision * sys_recall) / (sys_precision + sys_recall) if (sys_precision + sys_recall) > 0 else 0.0

    # 4. 1:N Identification Evaluation (Gallery vs Probe)
    print("\n[Step 4/4] Computing 1:N Identification Metrics (Rank-1 / Rank-5)...")
    gallery_identities = []
    gallery_embs = []
    for person_name, vid_path in gallery_dict.items():
        if vid_path in video_embeddings:
            gallery_identities.append(person_name)
            gallery_embs.append(video_embeddings[vid_path])

    gallery_embs = np.array(gallery_embs, dtype=np.float32)

    rank1_correct = 0
    rank5_correct = 0
    total_probes = 0

    for probe_vid, true_name in probe_list:
        if probe_vid in video_embeddings and len(gallery_embs) > 0:
            probe_emb = video_embeddings[probe_vid]
            sims = np.dot(gallery_embs, probe_emb)
            top_indices = np.argsort(sims)[::-1]

            top1_name = gallery_identities[top_indices[0]]
            top5_names = [gallery_identities[idx] for idx in top_indices[:5]]

            if top1_name == true_name:
                rank1_correct += 1
            if true_name in top5_names:
                rank5_correct += 1
            total_probes += 1

    rank1_acc = (rank1_correct / total_probes) if total_probes > 0 else 0.0
    rank5_acc = (rank5_correct / total_probes) if total_probes > 0 else 0.0

    results = {
        "dataset": "YouTube Faces Dataset (YTF)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_identities": len(id_map),
        "total_videos_analyzed": len(video_embeddings),
        "genuine_pairs_evaluated": len(gen_sims),
        "impostor_pairs_evaluated": len(imp_sims),
        "similarity_statistics": {
            "genuine_mean": float(np.mean(gen_sims)),
            "genuine_std": float(np.std(gen_sims)),
            "genuine_min": float(np.min(gen_sims)),
            "genuine_max": float(np.max(gen_sims)),
            "impostor_mean": float(np.mean(imp_sims)),
            "impostor_std": float(np.std(imp_sims)),
            "impostor_min": float(np.min(imp_sims)),
            "impostor_max": float(np.max(imp_sims)),
        },
        "verification_metrics": {
            "EER": round(eer * 100, 2),
            "EER_threshold": round(eer_threshold, 3),
            "TAR_at_FAR_1pct": round(tar_at_far_1pct * 100, 2),
            "threshold_at_FAR_1pct": round(thresh_1pct, 3),
            "TAR_at_FAR_01pct": round(tar_at_far_01pct * 100, 2),
            "threshold_at_FAR_01pct": round(thresh_01pct, 3),
            "current_system_threshold": {
                "threshold": sys_thresh,
                "accuracy": round(sys_accuracy * 100, 2),
                "precision": round(sys_precision * 100, 2),
                "recall": round(sys_recall * 100, 2),
                "F1_score": round(sys_f1 * 100, 2),
                "false_acceptance_rate": round(float(np.mean(imp_sims >= sys_thresh)) * 100, 3),
                "false_rejection_rate": round(float(np.mean(gen_sims < sys_thresh)) * 100, 2),
            },
        },
        "identification_metrics": {
            "gallery_size": len(gallery_embs),
            "probe_queries": total_probes,
            "rank1_accuracy": round(rank1_acc * 100, 2),
            "rank5_accuracy": round(rank5_acc * 100, 2),
        },
    }

    # Print Report Summary
    print("\n" + "=" * 75)
    print("                     BENCHMARK RESULTS SUMMARY")
    print("=" * 75)
    print(f"  • Genuine Mean Similarity:  {results['similarity_statistics']['genuine_mean']:.4f} (± {results['similarity_statistics']['genuine_std']:.4f})")
    print(f"  • Impostor Mean Similarity: {results['similarity_statistics']['impostor_mean']:.4f} (± {results['similarity_statistics']['impostor_std']:.4f})")
    print(f"  • EER (Equal Error Rate):   {results['verification_metrics']['EER']}% at threshold {results['verification_metrics']['EER_threshold']}")
    print(f"  • TAR @ FAR = 1.0%:         {results['verification_metrics']['TAR_at_FAR_1pct']}% (threshold = {results['verification_metrics']['threshold_at_FAR_1pct']})")
    print(f"  • TAR @ FAR = 0.1%:         {results['verification_metrics']['TAR_at_FAR_01pct']}% (threshold = {results['verification_metrics']['threshold_at_FAR_01pct']})")
    print("  --- Current System Config (Threshold = 0.55) ---")
    sys_m = results['verification_metrics']['current_system_threshold']
    print(f"  - Verification Accuracy:    {sys_m['accuracy']}%")
    print(f"  - Precision: {sys_m['precision']}% | Recall: {sys_m['recall']}% | F1: {sys_m['F1_score']}%")
    print(f"  - FAR: {sys_m['false_acceptance_rate']}% | FRR: {sys_m['false_rejection_rate']}%")
    print("  --- 1:N Identification (Gallery vs Probe) ---")
    print(f"  - Rank-1 Accuracy:          {results['identification_metrics']['rank1_accuracy']}%")
    print(f"  - Rank-5 Accuracy:          {results['identification_metrics']['rank5_accuracy']}%")
    print("=" * 75)

    out_path = output_json or str(RESULTS_DIR / "ytf_accuracy_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Results saved successfully to: {out_path}\n")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--identities", type=int, default=100, help="Number of identities to benchmark")
    args = parser.parse_args()

    run_ytf_accuracy_benchmark(max_identities=args.identities)
