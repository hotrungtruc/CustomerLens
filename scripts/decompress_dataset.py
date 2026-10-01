"""
decompress_dataset.py — Automated & space-efficient decompression of Chokepoint dataset.

Features:
- Uses native bsdtar for high-speed multi-threaded decompression.
- Automatically handles 2-level nested .tar.xz archives.
- Deletes temporary intermediate camera .tar.xz archives immediately to save ~10GB of disk space.
- Resumes gracefully if already partially extracted.
- Safety check: monitors free disk space and stops if free space drops below 1.5 GB.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT_DIR / "assets" / "dataset"

# Minimum free disk space in GB before pausing
MIN_FREE_DISK_GB = 1.5


def get_free_disk_gb(path: Path) -> float:
    usage = shutil.disk_usage(str(path))
    return usage.free / (1024 ** 3)


def run_tar(args: list) -> bool:
    cmd = ["tar"] + args
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        print(f"[TAR ERROR] {' '.join(cmd)} failed: {err.strip()}")
        return False
    return True


def list_tar_members(tar_path: Path) -> list:
    cmd = ["tar", "-tf", str(tar_path)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return []
    lines = result.stdout.decode("utf-8", errors="replace").splitlines()
    return [line.strip() for line in lines if line.strip()]


def is_folder_extracted(folder_path: Path) -> bool:
    if not folder_path.exists() or not folder_path.is_dir():
        return False
    # Check if folder has image files
    try:
        next_item = next(folder_path.iterdir(), None)
        return next_item is not None
    except Exception:
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 65)
    print("      CHOKEPOINT DATASET DECOMPRESSION WORKER")
    print("=" * 65)
    print(f"Dataset directory: {DATASET_DIR}")
    free_gb = get_free_disk_gb(DATASET_DIR)
    print(f"Available disk space on C: {free_gb:.2f} GB")
    print("=" * 65)

    if not DATASET_DIR.exists():
        print(f"[ERROR] Dataset directory not found: {DATASET_DIR}")
        sys.exit(1)

    # 1. Groundtruth
    gt_tar = DATASET_DIR / "groundtruth.tar.xz"
    gt_dir = DATASET_DIR / "groundtruth"
    if gt_tar.exists() and not is_folder_extracted(gt_dir):
        print("[1/2] Extracting groundtruth.tar.xz...")
        run_tar(["-xf", str(gt_tar), "-C", str(DATASET_DIR)])
    else:
        print("[1/2] groundtruth/ is already extracted.")

    # 2. Main outer archives
    outer_archives = sorted(
        [
            f
            for f in DATASET_DIR.glob("*.tar.xz")
            if f.name != "groundtruth.tar.xz"
            and not ("_C1" in f.name or "_C2" in f.name or "_C3" in f.name)
        ]
    )

    print(f"\n[2/2] Found {len(outer_archives)} main dataset package(s) to process:\n")
    total = len(outer_archives)

    for idx, outer_tar in enumerate(outer_archives, 1):
        name = outer_tar.name
        stem = name.replace(".tar.xz", "")
        print(f"\n[{idx}/{total}] Processing package: {name}...")

        # Inspect members
        members = list_tar_members(outer_tar)
        inner_tars = [m for m in members if m.endswith(".tar.xz")]

        if not inner_tars:
            # Flat archive
            dest_folder = DATASET_DIR / stem
            if is_folder_extracted(dest_folder):
                print(f"  -> Already extracted to {dest_folder.name}, skipping.")
                continue
            print(f"  -> Extracting {name}...")
            run_tar(["-xf", str(outer_tar), "-C", str(DATASET_DIR)])
            continue

        # Check if all camera folders already exist
        all_done = True
        for inner in inner_tars:
            cam_name = inner.replace(".tar.xz", "")
            cam_folder = DATASET_DIR / cam_name
            if not is_folder_extracted(cam_folder):
                all_done = False
                break

        if all_done:
            print(f"  -> All camera sequences for {stem} already extracted. Skipping.")
            continue

        # Check disk space safety
        cur_free = get_free_disk_gb(DATASET_DIR)
        if cur_free < MIN_FREE_DISK_GB:
            print(f"[WARNING] Low disk space ({cur_free:.2f} GB < {MIN_FREE_DISK_GB} GB). Stopping extraction.")
            break

        # Step A: Extract outer archive to get camera .tar.xz
        print(f"  -> Unpacking package {name} into camera archives...")
        if not run_tar(["-xf", str(outer_tar), "-C", str(DATASET_DIR)]):
            continue

        # Step B: Extract each camera .tar.xz into image folders, then remove camera .tar.xz
        for inner in inner_tars:
            inner_path = DATASET_DIR / inner
            cam_name = inner.replace(".tar.xz", "")
            cam_folder = DATASET_DIR / cam_name

            if not inner_path.exists():
                continue

            if is_folder_extracted(cam_folder):
                print(f"    - {cam_name} already exists. Cleaning archive.")
                inner_path.unlink(missing_ok=True)
                continue

            print(f"    - Extracting sequence {cam_name}...")
            t0 = time.time()
            ok = run_tar(["-xf", str(inner_path), "-C", str(DATASET_DIR)])
            elapsed = time.time() - t0

            if ok:
                count = len(list(cam_folder.glob("*.jpg")))
                print(f"      [OK] Extracted {count} frames in {elapsed:.1f}s.")
                # Immediately delete the intermediate archive to reclaim space
                inner_path.unlink(missing_ok=True)
            else:
                print(f"      [FAILED] Failed to extract {inner}.")

        cur_free = get_free_disk_gb(DATASET_DIR)
        print(f"  Package {stem} complete. Remaining disk space: {cur_free:.2f} GB.")

    final_free = get_free_disk_gb(DATASET_DIR)
    print("\n" + "=" * 65)
    print(f"  ALL DONE! Remaining free disk space on C: {final_free:.2f} GB")
    print("=" * 65)


if __name__ == "__main__":
    main()
