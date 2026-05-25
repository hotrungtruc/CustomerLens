import os
import urllib.request

from config import MODELS_DIR

MODELS = {
    "det_500m.onnx": "https://github.com/yakhyo/face-reidentification/releases/download/v0.0.1/det_500m.onnx",
    "w600k_mbf.onnx": "https://github.com/yakhyo/face-reidentification/releases/download/v0.0.1/w600k_mbf.onnx",
    "1k3d68.onnx": "https://huggingface.co/datasets/Alltitude/insightface/resolve/main/1k3d68.onnx",
    "2d106det.onnx": "https://huggingface.co/lytanshade/insightface/resolve/main/2d106det.onnx",
    "genderage.onnx": "https://huggingface.co/Arctic1998/insightface/resolve/main/genderage.onnx",
}


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

    print("All models ready.")


if __name__ == "__main__":
    main()
