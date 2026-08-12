import os
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

# Output directory for preview images
RAW_DATA_DIR = Path(r"C:\SCHOOL\asian_celeb_112x112_folders")
OUTPUT_TEST_DIR = Path(r"C:\SCHOOL\HK253\BigData\face-recognition-system\experiments\test_crop_output")
OUTPUT_TEST_DIR.mkdir(parents=True, exist_ok=True)

# Try MTCNN via facenet-pytorch or fallback to OpenCV Cascade
try:
    import torch
    from facenet_pytorch import MTCNN
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    detector = MTCNN(image_size=112, margin=14, post_process=False, device=device)
    HAS_MTCNN = True
    print(f"[INFO] Using MTCNN Face Detector on {device}")
except Exception as e:
    HAS_MTCNN = False
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    detector = cv2.CascadeClassifier(cascade_path)
    print(f"[INFO] Using OpenCV Haar Cascade Face Detector ({e})")

# Select 10 identity subfolders
subdirs = [d for d in RAW_DATA_DIR.iterdir() if d.is_dir()][:10]
print(f"[INFO] Selected 10 identity folders for preview test.")

results = []

for idx, folder in enumerate(subdirs, 1):
    img_files = list(folder.glob("*.*"))
    img_files = [f for f in img_files if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]]
    if not img_files:
        continue
        
    img_path = img_files[0]
    out_orig_path = OUTPUT_TEST_DIR / f"person_{idx:02d}_{folder.name}_raw.jpg"
    out_crop_path = OUTPUT_TEST_DIR / f"person_{idx:02d}_{folder.name}_cropped.jpg"
    
    # Save original image copy
    img_pil = Image.open(img_path).convert("RGB")
    img_pil.save(out_orig_path)
    
    # Crop Face
    crop_method = "MTCNN"
    if HAS_MTCNN:
        try:
            face_tensor = detector(img_pil)
            if face_tensor is not None:
                face_np = face_tensor.permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                cropped_img = Image.fromarray(face_np)
            else:
                crop_method = "CenterCrop (Fallback)"
                w, h = img_pil.size
                min_dim = min(w, h)
                cropped_img = img_pil.crop(((w-min_dim)//2, (h-min_dim)//2, (w+min_dim)//2, (h+min_dim)//2)).resize((112, 112))
        except Exception:
            crop_method = "CenterCrop (Fallback)"
            w, h = img_pil.size
            min_dim = min(w, h)
            cropped_img = img_pil.crop(((w-min_dim)//2, (h-min_dim)//2, (w+min_dim)//2, (h+min_dim)//2)).resize((112, 112))
    else:
        crop_method = "OpenCV Cascade"
        img_cv = cv2.imread(str(img_path))
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, 1.1, 4)
        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
            face_crop = img_cv[y:y+h, x:x+w]
            cropped_img = Image.fromarray(cv2.cvtColor(cv2.resize(face_crop, (112, 112)), cv2.COLOR_BGR2RGB))
        else:
            crop_method = "CenterCrop (Fallback)"
            w, h = img_pil.size
            min_dim = min(w, h)
            cropped_img = img_pil.crop(((w-min_dim)//2, (h-min_dim)//2, (w+min_dim)//2, (h+min_dim)//2)).resize((112, 112))
            
    cropped_img.save(out_crop_path)
    results.append({
        "folder": folder.name,
        "orig_size": img_pil.size,
        "crop_size": cropped_img.size,
        "method": crop_method,
        "raw_file": out_orig_path.name,
        "crop_file": out_crop_path.name
    })

print("\n" + "="*70)
print(f"RESULTS FOR 10 SAMPLE CROP TESTS:")
print("="*70)
for i, r in enumerate(results, 1):
    print(f"Sample {i:02d} | Identity: {r['folder']} | Method: {r['method']:<20} | Raw Size: {r['orig_size']} -> Crop Size: {r['crop_size']}")
print("="*70)
