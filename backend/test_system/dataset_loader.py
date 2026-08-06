import os
import random
from pathlib import Path
from typing import List, Tuple, Dict

DATASET_DEFAULT_PATH = r"C:\SCHOOL\asian_celeb_112x112_folders"

def get_sampled_identities(dataset_dir: str = DATASET_DEFAULT_PATH, num_identities: int = 300, seed: int = 42) -> List[str]:
    """Randomly sample N identities (subfolders) from dataset directory instantly using os.scandir."""
    if not os.path.exists(dataset_dir):
        raise FileNotFoundError(f"Dataset path does not exist: {dataset_dir}")
    
    valid_identities = []
    random.seed(seed)
    
    with os.scandir(dataset_dir) as entries:
        subdirs = [e.name for e in entries if e.is_dir()]
        
    random.shuffle(subdirs)
    
    for d in subdirs:
        sub_path = os.path.join(dataset_dir, d)
        try:
            with os.scandir(sub_path) as img_entries:
                images = [e.name for e in img_entries if e.is_file() and e.name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))]
            if len(images) >= 2:
                valid_identities.append(d)
                if len(valid_identities) >= num_identities:
                    break
        except Exception:
            continue
            
    print(f"[DatasetLoader] Sampled {len(valid_identities)} valid identities (>= 2 images each).")
    return valid_identities

def load_dataset_pairs(
    dataset_dir: str = DATASET_DEFAULT_PATH, 
    num_identities: int = 300, 
    seed: int = 42,
    num_neg_pairs_per_identity: int = 2
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], Dict[str, List[str]]]:
    """Generate 1:1 Verification Pairs:
    - Genuine Pairs (Same Person): (img1_path, img2_path) -> Label 1
    - Impostor Pairs (Different Person): (img1_path, img2_path) -> Label 0
    - Also returns identity map {identity_id: [img_paths]}
    """
    identities = get_sampled_identities(dataset_dir, num_identities, seed)
    
    identity_map: Dict[str, List[str]] = {}
    for identity in identities:
        sub_path = os.path.join(dataset_dir, identity)
        try:
            with os.scandir(sub_path) as entries:
                imgs = [
                    e.path
                    for e in entries
                    if e.is_file() and e.name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))
                ]
            identity_map[identity] = imgs
        except Exception:
            continue

    genuine_pairs = []
    for identity, imgs in identity_map.items():
        # Pick pairs within same identity
        for i in range(len(imgs) - 1):
            genuine_pairs.append((imgs[i], imgs[i + 1]))

    impostor_pairs = []
    identity_list = list(identity_map.keys())
    random.seed(seed)
    
    for i, id1 in enumerate(identity_list):
        img1 = random.choice(identity_map[id1])
        # Pick negative images from different identities
        other_ids = [id_x for id_x in identity_list if id_x != id1]
        neg_ids = random.sample(other_ids, min(num_neg_pairs_per_identity, len(other_ids)))
        for neg_id in neg_ids:
            img2 = random.choice(identity_map[neg_id])
            impostor_pairs.append((img1, img2))

    print(f"[DatasetLoader] Generated {len(genuine_pairs)} Genuine pairs and {len(impostor_pairs)} Impostor pairs.")
    return genuine_pairs, impostor_pairs, identity_map

def load_gallery_probe_split(
    identity_map: Dict[str, List[str]]
) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    """Generate 1:N Identification Gallery / Probe split.
    - Gallery: {identity_id: first_image_path} (1 reference face per person)
    - Probes: [(probe_image_path, true_identity_id)] (remaining images of each person)
    """
    gallery = {}
    probes = []
    
    for identity, imgs in identity_map.items():
        if len(imgs) > 0:
            gallery[identity] = imgs[0]
            for probe_img in imgs[1:]:
                probes.append((probe_img, identity))
                
    print(f"[DatasetLoader] Built Gallery with {len(gallery)} identities and {len(probes)} Probe queries.")
    return gallery, probes
