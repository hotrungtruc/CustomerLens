import os
import glob
import cv2
import time
import numpy as np
import matplotlib.pyplot as plt
import sys
from pathlib import Path

# Add backend to path to import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.core.insight_embedding import InsightEmbedder
from config import EDGEFACE_PATH

CELEBS_DATASET_PATH = r"C:\SCHOOL\asian_celeb_112x112_folders"
NUM_FOLDERS = 100
IMAGES_PER_FOLDER = 5

def cosine_similarity(emb1, emb2):
    return np.dot(emb1, emb2)

def main():
    print(f"Loading EdgeFace model from: {EDGEFACE_PATH}")
    app = InsightEmbedder(
        recognizer_path=EDGEFACE_PATH
    )
    
    person_folders = [f.path for f in os.scandir(CELEBS_DATASET_PATH) if f.is_dir()]
    person_folders = person_folders[:NUM_FOLDERS]
    
    embeddings = []
    labels = []
    inference_times = []
    
    print("Extracting embeddings...")
    for i, folder in enumerate(person_folders):
        folder_name = os.path.basename(folder)
        image_files = glob.glob(os.path.join(folder, "*.[jp][pn]*[g]"))
        
        for img_path in image_files[:IMAGES_PER_FOLDER]:
            img = cv2.imread(img_path)
            if img is None:
                continue
                
            # Resize small images to ensure face detection works
            h, w = img.shape[:2]
            if max(h, w) < 640:
                scale = 640 / max(h, w)
                img = cv2.resize(img, (int(w * scale), int(h * scale)))
                
            start_time = time.time()
            faces = app.get_faces(img)
            inf_time = time.time() - start_time
            
            if faces:
                # Take the most prominent face
                best_face = max(faces, key=lambda f: (f["bbox"][2]-f["bbox"][0])*(f["bbox"][3]-f["bbox"][1]))
                embeddings.append(best_face["embedding"])
                labels.append(folder_name)
                inference_times.append(inf_time)
                
        if (i+1) % 10 == 0:
            print(f"  Processed {i+1}/{len(person_folders)} folders...")
            
    print(f"Extracted {len(embeddings)} embeddings.")
    
    # Calculate pairwise matching
    print("Calculating Pairwise Cosine Similarity Matrix...")
    start_match = time.time()
    
    # Convert to numpy array (N, 512)
    embs_np = np.array(embeddings)
    # Cosine similarity matrix = dot product of normalized embeddings
    sim_matrix = np.dot(embs_np, embs_np.T)
    
    match_time = time.time() - start_match
    # Time per pair
    num_pairs = (len(embeddings) * (len(embeddings) - 1)) / 2
    avg_match_time_ms = (match_time / num_pairs) * 1000 if num_pairs > 0 else 0
    
    print(f"Matrix computed in {match_time:.4f} seconds.")
    print(f"Average Matching Time per pair: {avg_match_time_ms:.6f} ms")
    
    genuine_scores = []
    imposter_scores = []
    
    for i in range(len(embeddings)):
        for j in range(i+1, len(embeddings)):
            sim = sim_matrix[i, j]
            if labels[i] == labels[j]:
                genuine_scores.append(sim)
            else:
                imposter_scores.append(sim)
                
    genuine_scores = np.array(genuine_scores)
    imposter_scores = np.array(imposter_scores)
    
    print(f"Total Genuine pairs: {len(genuine_scores)}")
    print(f"Total Imposter pairs: {len(imposter_scores)}")
    
    thresholds = np.arange(0.50, 0.99, 0.01)
    far = []
    frr = []
    
    best_threshold = 0.50
    min_error_diff = float('inf')
    
    for t in thresholds:
        fa = np.sum(imposter_scores >= t) / len(imposter_scores) if len(imposter_scores) > 0 else 0
        fr = np.sum(genuine_scores < t) / len(genuine_scores) if len(genuine_scores) > 0 else 0
        far.append(fa)
        frr.append(fr)
        
        # EER approximation
        if abs(fa - fr) < min_error_diff:
            min_error_diff = abs(fa - fr)
            best_threshold = t
            
    print(f"Optimal Threshold (Approx EER): {best_threshold:.2f}")
    
    # Also find strict threshold where FAR < 0.01%
    strict_threshold = best_threshold
    for i, t in enumerate(thresholds):
        if far[i] < 0.001:  # 0.1% FAR
            strict_threshold = t
            break
            
    print(f"Strict Threshold (FAR < 0.1%): {strict_threshold:.2f}")
    
    # Plotting FAR/FRR
    plt.figure(figsize=(12, 5))
    
    plt.subplot(1, 2, 1)
    plt.plot(thresholds, far, label='False Acceptance Rate (FAR)', color='red')
    plt.plot(thresholds, frr, label='False Rejection Rate (FRR)', color='blue')
    plt.axvline(x=best_threshold, color='green', linestyle='--', label=f'EER Threshold ({best_threshold:.2f})')
    plt.axvline(x=strict_threshold, color='purple', linestyle=':', label=f'Strict Threshold ({strict_threshold:.2f})')
    plt.xlabel('Cosine Similarity Threshold')
    plt.ylabel('Error Rate')
    plt.title('FAR vs FRR for EdgeFace Model')
    plt.legend()
    plt.grid(True)
    
    # Plotting Response Times
    plt.subplot(1, 2, 2)
    avg_inf_ms = np.mean(inference_times) * 1000
    p95_inf_ms = np.percentile(inference_times, 95) * 1000
    
    metrics = ['Extraction (Avg)', 'Extraction (P95)', 'Matching (per pair)']
    times = [avg_inf_ms, p95_inf_ms, avg_match_time_ms]
    
    bars = plt.bar(metrics, times, color=['skyblue', 'orange', 'lightgreen'])
    plt.ylabel('Time (ms)')
    plt.title('Response Time Metrics')
    
    # Add values on top of bars
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, yval, f'{yval:.2f}ms', ha='center', va='bottom')
        
    plt.tight_layout()
    plot_path = os.path.join(os.path.dirname(__file__), "edgeface_evaluation.png")
    plt.savefig(plot_path)
    print(f"Evaluation plot saved to {plot_path}")

if __name__ == "__main__":
    main()
