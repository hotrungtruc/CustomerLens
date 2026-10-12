"""
YTF (YouTube Faces) Dataset Loader for CustomerLens Benchmark System.
Loads processed .npz files containing color video frames, bounding boxes, and 2D/3D landmarks.
"""

import os
import glob
import random
from typing import Dict, List, Tuple, Any
import numpy as np

YTF_DEFAULT_DIR = r"c:\PROJECTS\CustomerLens\assets\YTF\youtube_faces_with_keypoints_full_1"


def get_ytf_identities(
    dataset_dir: str = YTF_DEFAULT_DIR,
    min_videos: int = 2,
    max_identities: int | None = None,
    seed: int = 42,
) -> Dict[str, List[str]]:
    """
    Scans dataset_dir and groups all .npz video paths by person identity.
    Returns: {person_name: [list_of_npz_paths]} for identities with >= min_videos.
    """
    if not os.path.exists(dataset_dir):
        raise FileNotFoundError(f"YTF dataset directory does not exist: {dataset_dir}")

    npz_files = glob.glob(os.path.join(dataset_dir, "*.npz"))
    identity_map: Dict[str, List[str]] = {}

    for path in npz_files:
        basename = os.path.splitext(os.path.basename(path))[0]
        # Filename format: {Person_Name}_{video_num}
        parts = basename.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            person_name = parts[0]
        else:
            person_name = basename
        identity_map.setdefault(person_name, []).append(path)

    # Filter identities with at least min_videos
    valid_map = {k: sorted(v) for k, v in identity_map.items() if len(v) >= min_videos}

    # Deterministic sampling if max_identities is set
    all_keys = sorted(valid_map.keys())
    if max_identities is not None and max_identities < len(all_keys):
        rng = random.Random(seed)
        sampled_keys = rng.sample(all_keys, max_identities)
        valid_map = {k: valid_map[k] for k in sampled_keys}

    return valid_map


def load_ytf_video(npz_path: str) -> Dict[str, np.ndarray]:
    """
    Loads an .npz file and returns dictionary of arrays:
      - 'colorImages': (H, W, 3, N_frames) uint8 RGB
      - 'boundingBox': (4, 2, N_frames) float64
      - 'landmarks2D': (68, 2, N_frames) float64
      - 'landmarks3D': (68, 3, N_frames) float64
    """
    data = np.load(npz_path)
    return {
        "colorImages": data["colorImages"],
        "boundingBox": data["boundingBox"],
        "landmarks2D": data["landmarks2D"],
        "landmarks3D": data["landmarks3D"],
        "num_frames": data["colorImages"].shape[-1],
        "height": data["colorImages"].shape[0],
        "width": data["colorImages"].shape[1],
    }


def get_ytf_verification_pairs(
    dataset_dir: str = YTF_DEFAULT_DIR,
    max_identities: int = 150,
    num_impostors_per_id: int = 3,
    seed: int = 42,
) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str, str, str]], Dict[str, List[str]]]:
    """
    Generates 1:1 Verification Pairs across different videos:
      - Genuine Pairs (Same Person, Different Videos):
          (video_A_path, video_B_path, person_name)
      - Impostor Pairs (Different Persons):
          (video_A_path, video_B_path, person_A_name, person_B_name)
    """
    identity_map = get_ytf_identities(dataset_dir, min_videos=2, max_identities=max_identities, seed=seed)
    rng = random.Random(seed)

    genuine_pairs: List[Tuple[str, str, str]] = []
    for person_name, video_paths in identity_map.items():
        # Pick all combinations or sequential pairs of different videos of this person
        for i in range(len(video_paths) - 1):
            genuine_pairs.append((video_paths[i], video_paths[i + 1], person_name))

    impostor_pairs: List[Tuple[str, str, str, str]] = []
    identities = list(identity_map.keys())

    for person_a in identities:
        vid_a = rng.choice(identity_map[person_a])
        other_people = [p for p in identities if p != person_a]
        sampled_others = rng.sample(other_people, min(num_impostors_per_id, len(other_people)))
        for person_b in sampled_others:
            vid_b = rng.choice(identity_map[person_b])
            impostor_pairs.append((vid_a, vid_b, person_a, person_b))

    return genuine_pairs, impostor_pairs, identity_map


def get_ytf_gallery_probe_split(
    identity_map: Dict[str, List[str]]
) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    """
    Creates 1:N Identification split:
      - Gallery: {person_name: first_video_path} (Enrollment / Reference)
      - Probes: [(probe_video_path, true_person_name)] (Subsequent returning videos)
    """
    gallery: Dict[str, str] = {}
    probes: List[Tuple[str, str]] = []

    for person_name, videos in identity_map.items():
        if videos:
            gallery[person_name] = videos[0]
            for probe_vid in videos[1:]:
                probes.append((probe_vid, person_name))

    return gallery, probes
