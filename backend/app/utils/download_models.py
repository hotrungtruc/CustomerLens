import os
import urllib.request

from config import MODELS_DIR

MODELS = {
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "ghostface_fp32.onnx": "https://github.com/andestech/ModelZoo/raw/master/GhostFaceNet/Model/ghostface_fp32.onnx",
}





def build_ghostface_int8():
    src_path = MODELS_DIR / "ghostface_fp32.onnx"
    dst_path = MODELS_DIR / "ghostface_int8.onnx"

    if dst_path.exists():
        print("ghostface_int8.onnx already exists")
        return

    if not src_path.exists():
        print("ghostface_fp32.onnx is missing; cannot build ghostface_int8.onnx")
        return

    try:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        quantize_dynamic(str(src_path), str(dst_path), weight_type=QuantType.QInt8)
        print(f"Built int8 model: {dst_path}")
    except Exception as exc:
        print(f"Failed to build ghostface_int8.onnx: {exc}")


def download_file(url, filename):
    try:
        save_path = MODELS_DIR / filename
        req = urllib.request.Request(url)
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )

        with urllib.request.urlopen(req, timeout=300) as response:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(save_path, "wb") as out_file:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(
                            f"{filename}: {percent:.1f}% "
                            f"({downloaded / (1024 * 1024):.1f}MB / "
                            f"{total_size / (1024 * 1024):.1f}MB)",
                            end="\r",
                        )

        print(f"Saved to {save_path}")
    except Exception as e:
        print(f"Download failed: {e}")


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in MODELS.items():
        save_path = MODELS_DIR / filename

        if save_path.exists():
            print(f"{filename} already exists")
        else:
            download_file(url, filename)

    build_ghostface_int8()

    print("All models ready.")


if __name__ == "__main__":
    main()
