"""
run_edge.py — Edge Device Runner CLI.

Starts video capture from Webcam, RTSP stream, or video file,
runs SCRFD-500M + EdgeFace γ0.5 + Tracker, and streams face events to Cloud.

Examples:
  python -m edge.run_edge --source 0 --preview
  python -m edge.run_edge --source rtsp://admin:pass@192.168.1.100:554/stream1 --camera-id CAM_GATE
  python -m edge.run_edge --source test.mp4 --cloud-url http://localhost:8000
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

import cv2
from edge.edge_config import DEFAULT_CAMERA_ID, DEFAULT_CLOUD_URL, DEFAULT_DEVICE_ID
from edge.edge_pipeline import EdgePipeline


def main():
    parser = argparse.ArgumentParser(description="Front Door AI Edge Device Agent")
    parser.add_argument("--source", default="0", help="Video source: camera index (0), RTSP url, or video file path")
    parser.add_argument("--cloud-url", default=DEFAULT_CLOUD_URL, help=f"Cloud backend URL (default: {DEFAULT_CLOUD_URL})")
    parser.add_argument("--camera-id", default=DEFAULT_CAMERA_ID, help=f"Camera ID (default: {DEFAULT_CAMERA_ID})")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help=f"Device ID (default: {DEFAULT_DEVICE_ID})")
    parser.add_argument("--preview", action="store_true", help="Display local GUI preview window")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 for infinite)")

    args = parser.parse_args()

    # Determine capture source
    source = args.source
    if source.isdigit():
        source = int(source)

    print("=" * 65)
    print("      FRONT DOOR AI — EDGE INTELLIGENT DEVICE AGENT")
    print("=" * 65)
    print(f"  • Source    : {source}")
    print(f"  • Cloud URL : {args.cloud_url}")
    print(f"  • Camera ID : {args.camera_id}")
    print(f"  • Device ID : {args.device_id}")
    print(f"  • Preview   : {'Enabled' if args.preview else 'Headless'}")
    print("=" * 65)

    pipeline = EdgePipeline(
        cloud_url=args.cloud_url,
        camera_id=args.camera_id,
        device_id=args.device_id,
    )

    is_image = isinstance(source, str) and any(source.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"])
    image_frame = None
    cap = None

    if is_image:
        image_frame = cv2.imread(source)
        if image_frame is None:
            print(f"[ERROR] Could not read image file: {source}")
            sys.exit(1)
        print(f"[Edge Runner] Simulated camera stream from image: {source} ({image_frame.shape[1]}x{image_frame.shape[0]})")
    else:
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"[ERROR] Could not open video source: {source}")
            sys.exit(1)

        # Set camera resolution if webcam
        if isinstance(source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    print("[Edge Pipeline] Streaming started. Press Ctrl+C (or 'q' in preview) to stop.\n")
    frame_idx = 0

    try:
        while True:
            if is_image:
                frame = image_frame.copy()
                time.sleep(0.04)  # Simulate 25 FPS
            else:
                ret, frame = cap.read()
                if not ret:
                    # If video file reached end, loop or exit
                    if isinstance(source, str) and not source.startswith("rtsp://"):
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    else:
                        print("[WARNING] Frame capture dropped or stream disconnected. Retrying...")
                        time.sleep(0.5)
                        continue

            frame_idx += 1
            annotated, tracks = pipeline.process_frame(frame)

            if args.preview:
                cv2.imshow(f"Edge AI - {args.camera_id}", annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:
                    break

            if args.max_frames > 0 and frame_idx >= args.max_frames:
                print(f"[Edge Runner] Reached max frames limit ({args.max_frames}). Stopping.")
                break

    except KeyboardInterrupt:
        print("\n[Edge Pipeline] Stopping gracefully...")
    finally:
        pipeline.close()
        if cap is not None:
            cap.release()
        if args.preview:
            cv2.destroyAllWindows()
        print("[Edge Pipeline] Stopped.")


if __name__ == "__main__":
    main()
