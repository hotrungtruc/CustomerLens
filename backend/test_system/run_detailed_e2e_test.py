import asyncio
import csv
import glob
import hashlib
import json
import os
import sys

# Force UTF-8 encoding for standard output to avoid Windows charmap errors
sys.stdout.reconfigure(encoding='utf-8')

import uuid
from typing import List, Dict, Optional

import cv2
import websockets

# Add backend directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.connection import get_db_connection, create_camera_and_credential

CELEBS_DATASET_PATH = r"C:\SCHOOL\asian_celeb_112x112_folders"
TWINS_DATASET_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "images")

CAMERA_ID = "cam_e2e_test"
CAMERA_NAME = "E2E Test Camera"
WS_URL = f"ws://localhost:8000/ws/{CAMERA_ID}?takeover=1"

# Burst mode settings
MAX_RETRIES_PER_IMAGE = 100
RETRY_DELAY_SECONDS = 0.3

def setup_test_camera() -> str:
    """Inject a fake camera credential into the database and return the token."""
    print("[Setup] Initializing test camera credentials in Database...")
    token = f"e2e_test_token_{uuid.uuid4().hex}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    credential_id = f"cred_{uuid.uuid4().hex[:8]}"

    conn = get_db_connection()
    try:
        # Check if camera exists, if so, delete it to start fresh
        conn.execute("DELETE FROM camera_device_credentials WHERE camera_id = ?", (CAMERA_ID,))
        conn.execute("DELETE FROM cameras WHERE camera_id = ?", (CAMERA_ID,))
        # Clean up legacy test data to prevent Dirty DB matching
        conn.execute("DELETE FROM customer_embeddings WHERE customer_id LIKE 'GUEST_cam_e2e_test_%'")
        conn.execute("DELETE FROM customers WHERE customer_id LIKE 'GUEST_cam_e2e_test_%'")
        
        create_camera_and_credential(
            conn=conn,
            camera_id=CAMERA_ID,
            display_name=CAMERA_NAME,
            credential_id=credential_id,
            token_hash=token_hash
        )
        conn.commit()
        print(f"[Setup] Successfully created test camera '{CAMERA_ID}' with token.")
        return token
    except Exception as e:
        print(f"[Setup] Error setting up camera: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

def encode_image(image_path: str) -> tuple[bytes, int, int]:
    """Read image, resize if necessary, and encode as binary JPEG."""
    frame = cv2.imread(image_path)
    if frame is None:
        raise ValueError(f"Could not read image: {image_path}")
    
    # Resize to at least 640 max dim to ensure face bbox > 80px
    # Only upscale small images, do not downscale large images
    min_max_dim = 640
    h, w = frame.shape[:2]
    if max(h, w) < min_max_dim:
        scale = min_max_dim / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        
    _, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return buffer.tobytes(), frame.shape[1], frame.shape[0]

async def send_image_burst(ws, image_bytes: bytes, w: int, h: int, is_aligned_crop: bool = False, expected_faces: int = 1) -> List[Dict]:
    """
    Send the same image repeatedly (Burst Mode).
    """
    # Clear any pending messages in the websocket queue
    while True:
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.01)
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            break

    # Build payload
    if is_aligned_crop:
        scale = w / 112.0
        landmarks = [
            [38.2946 * scale, 51.6963 * scale],
            [73.5318 * scale, 51.5014 * scale],
            [56.0252 * scale, 71.7366 * scale],
            [41.5493 * scale, 92.3655 * scale],
            [70.7299 * scale, 92.2041 * scale]
        ]
        meta_dict = {
            "local_track_id": f"celeb_track_{uuid.uuid4().hex[:8]}",
            "landmarks": landmarks,
            "bbox": [0, 0, w, h]
        }
        meta_json = json.dumps(meta_dict).encode("utf-8")
        meta_len_out = len(meta_json).to_bytes(4, byteorder="big")
        payload = meta_len_out + meta_json + image_bytes
    else:
        # Standard protocol (just bytes)
        payload = image_bytes

    for attempt in range(MAX_RETRIES_PER_IMAGE):
        try:
            await ws.send(payload)
            
            # Wait for response
            response_text = await asyncio.wait_for(ws.recv(), timeout=0.5)
            response = json.loads(response_text)
            
            if response.get("type") == "camera_update":
                customers = response.get("customers", [])
                
                # Check if system resolved ANY customer to a GUEST_ ID
                resolved_customers = []
                for c in customers:
                    if c.get("id") and c["id"].startswith("GUEST_"):
                        resolved_customers.append(c)
                
                if len(resolved_customers) >= expected_faces:
                    return resolved_customers
                else:
                    # Print what it got instead
                    if attempt % 10 == 0:
                        ids = [c.get("id") for c in customers]
                        print(f"      [Debug] attempt {attempt}: Got update, but no resolved GUEST_ ID yet. IDs: {ids}")
                    
        except asyncio.TimeoutError:
            # No response (maybe frame was dropped by ai_worker), retry
            if attempt % 10 == 0:
                print(f"      [Debug] attempt {attempt}: Timeout waiting for WS response.")
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            continue
        except websockets.exceptions.ConnectionClosed as e:
            print(f"\n[Error] WebSocket connection closed unexpectedly: {e}")
            raise e
        except json.JSONDecodeError:
            continue
            
    # If we exhausted retries and found no face / no resolved guest
    return []

async def test_celebs_dataset(ws, num_folders: int = 100, images_per_folder: int = 5):
    print(f"\n--- Starting Celebs Dataset Test ({num_folders} people, {images_per_folder} images each) ---")
    
    if not os.path.exists(CELEBS_DATASET_PATH):
        print(f"Error: Celebs path {CELEBS_DATASET_PATH} not found!")
        return []

    person_folders = [f.path for f in os.scandir(CELEBS_DATASET_PATH) if f.is_dir()]
    person_folders = person_folders[:num_folders]
    
    results = []
    
    for i, folder in enumerate(person_folders):
        folder_name = os.path.basename(folder)
        image_files = glob.glob(os.path.join(folder, "*.[jp][pn]*[g]"))
        
        if not image_files:
            continue
            
        test_images = image_files[:images_per_folder]
        expected_guest_id = None
        
        print(f"\n[{i+1}/{len(person_folders)}] Testing Celeb: {folder_name} ({len(test_images)} images)")
        
        for j, img_path in enumerate(test_images):
            img_name = os.path.basename(img_path)
            try:
                img_bytes, w, h = encode_image(img_path)
                customers = await send_image_burst(ws, img_bytes, w, h, is_aligned_crop=True)
                
                if not customers:
                    status = "Fail: Detection"
                    actual_id = "None"
                    print(f"  Img {j+1}: {img_name} -> FAILED (No face detected or ID not resolved)")
                else:
                    # Take the most prominent face
                    actual_id = customers[0].get("id")
                    
                    if j == 0:
                        # First image establishes the expected ID
                        expected_guest_id = actual_id
                        status = "Pass: Initialized"
                        print(f"  Img {j+1}: {img_name} -> {actual_id} (INITIALIZED)")
                    else:
                        # Subsequent images must match expected ID
                        if actual_id == expected_guest_id:
                            status = "Pass: Matched"
                            print(f"  Img {j+1}: {img_name} -> {actual_id} (MATCHED)")
                        else:
                            status = f"Fail: Confusion"
                            print(f"  Img {j+1}: {img_name} -> {actual_id} (CONFUSION - expected {expected_guest_id})")
                            
            except Exception as e:
                status = f"Fail: Error ({str(e)})"
                actual_id = "Error"
                print(f"  Img {j+1}: {img_name} -> ERROR: {e}")
                
            results.append({
                "Folder": folder_name,
                "Image": img_name,
                "Expected_ID": expected_guest_id if j > 0 else "N/A",
                "Actual_ID": actual_id,
                "Status": status
            })
            
            # Small delay between frames of same person
            await asyncio.sleep(0.5)
            
        # Large delay between different people to let the tracker reset
        await asyncio.sleep(2)
        
    return results

async def test_twins_dataset(ws):
    print(f"\n--- Starting Twins Dataset Test ---")
    
    if not os.path.exists(TWINS_DATASET_PATH):
        print(f"Error: Twins path {TWINS_DATASET_PATH} not found!")
        return []
        
    image_files = glob.glob(os.path.join(TWINS_DATASET_PATH, "*.[jp][pn]*[g]"))
    results = []
    
    for j, img_path in enumerate(image_files):
        img_name = os.path.basename(img_path)
        print(f"\n[{j+1}/{len(image_files)}] Testing Twins Image: {img_name}")
        
        try:
            img_bytes, w, h = encode_image(img_path)
            customers = await send_image_burst(ws, img_bytes, w, h, is_aligned_crop=False, expected_faces=2)
            
            detected_faces = len(customers)
            assigned_ids = [c.get("id") for c in customers]
            
            # Evaluation logic for twins
            if detected_faces == 2:
                if assigned_ids[0] == assigned_ids[1]:
                    status = "Fail: Same ID assigned to both twins!"
                else:
                    status = "Pass: Differentiated successfully"
            elif detected_faces == 1:
                status = "Info: Only 1 face detected in this image."
            else:
                status = "Fail: No faces or >2 faces detected."
                
            print(f"  Detected {detected_faces} face(s). IDs: {assigned_ids} -> {status}")
            
            results.append({
                "Image": img_name,
                "Detected_Faces": detected_faces,
                "Assigned_IDs": " | ".join(assigned_ids),
                "Status": status
            })
            
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "Image": img_name,
                "Detected_Faces": 0,
                "Assigned_IDs": "Error",
                "Status": f"Error: {e}"
            })
            
        await asyncio.sleep(2)
        
    return results

def write_csv(filename: str, data: List[Dict]):
    if not data:
        return
    keys = data[0].keys()
    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)
    print(f"\nSaved report to {filepath}")

async def main():
    token = setup_test_camera()
    headers = {
        "Cookie": f"device_token={token}",
        "Origin": "http://localhost:3000"
    }
    
    print(f"\n[Connecting] Establishing WebSocket to {WS_URL} ...")
    try:
        # Use additional_headers for newer websockets versions
        async with websockets.connect(WS_URL, additional_headers=headers) as ws:
            print("[Connected] WebSocket connection successful.")
            
            # Wait a moment for backend to initialize track manager
            await asyncio.sleep(1)
            
            # Run Celeb Test
            celeb_results = await test_celebs_dataset(ws, num_folders=10, images_per_folder=5)
            write_csv("results_10_celebs.csv", celeb_results)
            
            # Run Twins Test
            twin_results = await test_twins_dataset(ws)
            write_csv("results_twins.csv", twin_results)
            
    except Exception as e:
        print(f"[Fatal] Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
