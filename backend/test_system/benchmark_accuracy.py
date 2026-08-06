import os
import sys
import time
import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.insight_embedding import InsightEmbedder
from test_system.dataset_loader import (
    load_dataset_pairs,
    load_gallery_probe_split,
    DATASET_DEFAULT_PATH,
)

def compute_cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """Compute cosine similarity between two 1D normalized embeddings."""
    norm1 = np.linalg.norm(emb1)
    norm2 = np.linalg.norm(emb2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(emb1, emb2) / (norm1 * norm2))

def evaluate_accuracy(
    dataset_dir: str = DATASET_DEFAULT_PATH,
    num_identities: int = 300,
    output_json: str = None,
    embedder: InsightEmbedder = None,
) -> Dict:
    print("=" * 70)
    print(f"  AI ACCURACY BENCHMARK (1:1 Verification & 1:N Identification)")
    print(f"  Dataset: {dataset_dir}")
    print(f"  Target Identities: {num_identities}")
    print("=" * 70)

    # 1. Load dataset split
    genuine_pairs, impostor_pairs, identity_map = load_dataset_pairs(
        dataset_dir=dataset_dir, num_identities=num_identities, seed=42
    )
    gallery, probes = load_gallery_probe_split(identity_map)

    # Collect all unique image paths
    all_images = set()
    for img1, img2 in genuine_pairs:
        all_images.add(img1)
        all_images.add(img2)
    for img1, img2 in impostor_pairs:
        all_images.add(img1)
        all_images.add(img2)

    print(f"\n[1/4] Extracting embeddings for {len(all_images)} unique face images...")
    if embedder is None:
        embedder = InsightEmbedder()
    embedding_cache: Dict[str, np.ndarray] = {}

    start_time = time.time()
    extracted_count = 0
    failed_count = 0

    for idx, img_path in enumerate(all_images, 1):
        if idx % 50 == 0 or idx == len(all_images):
            print(f"  Processing image {idx}/{len(all_images)} ({(idx/len(all_images))*100:.1f}%)...")
            sys.stdout.flush()
        img = cv2.imread(img_path)
        if img is None:
            failed_count += 1
            continue
        
        # Enforce 5-Point Landmark Affine Alignment for precise biometrics
        h, w = img.shape[:2]
        lm5_template = np.array([
            [w * 0.3419, h * 0.4616],
            [w * 0.6565, h * 0.4598],
            [w * 0.5002, h * 0.6405],
            [w * 0.3710, h * 0.8247],
            [w * 0.6315, h * 0.8232]
        ], dtype=np.float32)
        emb = embedder.get_embedding(img, landmarks=lm5_template)
        if emb is not None and len(emb) > 0:
            embedding_cache[img_path] = np.asarray(emb, dtype=np.float32).reshape(-1)
            extracted_count += 1
        else:
            failed_count += 1

    extraction_duration = time.time() - start_time
    print(f"  Embedding extraction completed in {extraction_duration:.2f}s ({extracted_count} success, {failed_count} failed).")

    # 2. Evaluate 1:1 Verification
    print("\n[2/4] Evaluating 1:1 Face Verification (Genuine vs Impostor Pairs)...")
    genuine_scores = []
    for img1, img2 in genuine_pairs:
        if img1 in embedding_cache and img2 in embedding_cache:
            score = compute_cosine_similarity(embedding_cache[img1], embedding_cache[img2])
            genuine_scores.append(score)

    impostor_scores = []
    for img1, img2 in impostor_pairs:
        if img1 in embedding_cache and img2 in embedding_cache:
            score = compute_cosine_similarity(embedding_cache[img1], embedding_cache[img2])
            impostor_scores.append(score)

    genuine_scores = np.array(genuine_scores)
    impostor_scores = np.array(impostor_scores)

    print(f"  Computed {len(genuine_scores)} Genuine scores and {len(impostor_scores)} Impostor scores.")

    # Calculate EER, Thresholds, TAR @ FAR
    thresholds = np.linspace(0.0, 1.0, 1001)
    far_list = []
    frr_list = []
    tar_list = []

    for th in thresholds:
        far = np.mean(impostor_scores >= th) if len(impostor_scores) > 0 else 0.0
        frr = np.mean(genuine_scores < th) if len(genuine_scores) > 0 else 0.0
        tar = 1.0 - frr
        far_list.append(far)
        frr_list.append(frr)
        tar_list.append(tar)

    far_arr = np.array(far_list)
    frr_arr = np.array(frr_list)

    # Find EER point where |FAR - FRR| is minimal
    eer_idx = np.argmin(np.abs(far_arr - frr_arr))
    eer = float((far_arr[eer_idx] + frr_arr[eer_idx]) / 2.0)
    optimal_threshold = float(thresholds[eer_idx])

    # Calculate TAR @ FAR = 0.001 (0.1%)
    far_target_1e3 = 0.001
    idx_1e3 = np.argmin(np.abs(far_arr - far_target_1e3))
    tar_at_far_1e3 = float(tar_list[idx_1e3])
    th_1e3 = float(thresholds[idx_1e3])

    # Calculate TAR @ FAR = 0.0001 (0.01%)
    far_target_1e4 = 0.0001
    idx_1e4 = np.argmin(np.abs(far_arr - far_target_1e4))
    tar_at_far_1e4 = float(tar_list[idx_1e4])
    th_1e4 = float(thresholds[idx_1e4])

    # Precision / Recall / F1 at optimal threshold
    tp = np.sum(genuine_scores >= optimal_threshold)
    fp = np.sum(impostor_scores >= optimal_threshold)
    fn = np.sum(genuine_scores < optimal_threshold)
    tn = np.sum(impostor_scores < optimal_threshold)

    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1_score = float(2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    print(f"  [1:1 Results]")
    print(f"    - Equal Error Rate (EER): {eer * 100:.2f}% (at Cosine Threshold = {optimal_threshold:.4f})")
    print(f"    - TAR @ FAR=0.1% (1e-3) : {tar_at_far_1e3 * 100:.2f}% (Threshold = {th_1e3:.4f})")
    print(f"    - TAR @ FAR=0.01% (1e-4): {tar_at_far_1e4 * 100:.2f}% (Threshold = {th_1e4:.4f})")
    print(f"    - Precision @ th*       : {precision * 100:.2f}%")
    print(f"    - Recall @ th*          : {recall * 100:.2f}%")
    print(f"    - F1-Score @ th*        : {f1_score * 100:.2f}%")

    # 3. Evaluate 1:N Identification
    print("\n[3/4] Evaluating 1:N Identification (Gallery vs Probe Search)...")
    gallery_embeddings = {}
    for identity, img_path in gallery.items():
        if img_path in embedding_cache:
            gallery_embeddings[identity] = embedding_cache[img_path]

    rank1_correct = 0
    rank5_correct = 0
    total_probes_evaluated = 0

    gallery_identities = list(gallery_embeddings.keys())
    gallery_matrix = np.array([gallery_embeddings[id_] for id_ in gallery_identities])

    for probe_img, true_id in probes:
        if probe_img not in embedding_cache or true_id not in gallery_embeddings:
            continue

        probe_emb = embedding_cache[probe_img]
        # Compute cosine similarities against all gallery faces
        sims = np.dot(gallery_matrix, probe_emb) / (
            np.linalg.norm(gallery_matrix, axis=1) * np.linalg.norm(probe_emb) + 1e-10
        )

        top_indices = np.argsort(sims)[::-1]
        top_identities = [gallery_identities[idx] for idx in top_indices[:5]]

        total_probes_evaluated += 1
        if top_identities[0] == true_id:
            rank1_correct += 1
        if true_id in top_identities:
            rank5_correct += 1

    rank1_acc = float(rank1_correct / total_probes_evaluated) if total_probes_evaluated > 0 else 0.0
    rank5_acc = float(rank5_correct / total_probes_evaluated) if total_probes_evaluated > 0 else 0.0

    print(f"  [1:N Results]")
    print(f"    - Total Probes Tested: {total_probes_evaluated}")
    print(f"    - Rank-1 Accuracy    : {rank1_acc * 100:.2f}% ({rank1_correct}/{total_probes_evaluated})")
    print(f"    - Rank-5 Accuracy    : {rank5_acc * 100:.2f}% ({rank5_correct}/{total_probes_evaluated})")

    # 4. Compile & Export Results
    results = {
        "dataset": dataset_dir,
        "num_identities_evaluated": len(identity_map),
        "total_images_processed": len(all_images),
        "extraction_duration_sec": round(extraction_duration, 2),
        "verification_1to1": {
            "genuine_pairs_count": len(genuine_scores),
            "impostor_pairs_count": len(impostor_scores),
            "eer_percentage": round(eer * 100, 2),
            "optimal_cosine_threshold": round(optimal_threshold, 4),
            "tar_at_far_1e3_percentage": round(tar_at_far_1e3 * 100, 2),
            "tar_at_far_1e4_percentage": round(tar_at_far_1e4 * 100, 2),
            "precision_percentage": round(precision * 100, 2),
            "recall_percentage": round(recall * 100, 2),
            "f1_score_percentage": round(f1_score * 100, 2),
            "mean_genuine_similarity": round(float(np.mean(genuine_scores)), 4),
            "mean_impostor_similarity": round(float(np.mean(impostor_scores)), 4),
        },
        "identification_1toN": {
            "gallery_size": len(gallery_embeddings),
            "probes_evaluated": total_probes_evaluated,
            "rank1_accuracy_percentage": round(rank1_acc * 100, 2),
            "rank5_accuracy_percentage": round(rank5_acc * 100, 2),
        }
    }

    if output_json:
        os.makedirs(os.path.dirname(output_json), exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[4/4] Saved Accuracy Benchmark results to: {output_json}")

    return results

if __name__ == "__main__":
    results_dir = os.path.join(backend_dir, "test_system", "results")
    output_path = os.path.join(results_dir, "accuracy_results.json")
    evaluate_accuracy(num_identities=300, output_json=output_path)
