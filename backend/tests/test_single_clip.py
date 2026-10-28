import sys
sys.path.insert(0, ".")
try:
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    sys.stderr.reconfigure(line_buffering=True, encoding="utf-8")
except Exception:
    pass
import cv2
import numpy as np
from pathlib import Path
from app.api.devices import _process_crop_direct
from app.core.insight_embedding import get_embedder

embedder = get_embedder()
cap = cv2.VideoCapture("c:/PROJECTS/CustomerLens/assets/YTF/converted_videos/Bill_Clinton_0.mp4")
passed = 0
total = 0

from app.core.tracking.guest_tracker import GuestTrackManager

track_manager = GuestTrackManager(
    buffer_size=2,
    guest_creation_buffer_size=3,
    similarity_threshold=0.65,
    guest_prefix="LN",
)

while cap.isOpened() and total < 10:
    ret, frame = cap.read()
    if not ret:
        break
    total += 1
    dets = embedder.detect(frame)
    if len(dets[0]) == 0:
        continue
    box = dets[0][0]
    x1, y1, x2, y2 = map(int, box)
    bw, bh = x2 - x1, y2 - y1
    pad_x, pad_y = int(bw * 0.3), int(bh * 0.3)
    h, w = frame.shape[:2]
    crop = frame[max(0, y1 - pad_x):min(h, y2 + pad_y), max(0, x1 - pad_x):min(w, x2 + pad_x)]
    _, buf = cv2.imencode(".jpg", crop)
    meta = {"local_track_id": "test_track_1", "bbox": [x1, y1, x2, y2], "score": float(dets[2][0])}
    res = _process_crop_direct(buf.tobytes(), meta, "test_cam", "test_conn")
    if res is not None:
        passed += 1
        tracked = track_manager.process_faces(res["face_records"])
        print(f"Frame {total}: PASS -> tracked: {tracked}")
    else:
        print(f"Frame {total}: FAIL")

print(f"Total passed: {passed}/{total}")

