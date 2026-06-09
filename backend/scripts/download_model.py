import os
import urllib.request
from pathlib import Path

def download_model(url, dest_path):
    print(f"Downloading {url} to {dest_path}...")
    try:
        urllib.request.urlretrieve(url, dest_path)
        print("Download complete.")
    except Exception as e:
        print(f"Failed to download: {e}")
        print("Please ensure the URL is correct or manually place the ONNX file in the models directory.")

if __name__ == "__main__":
    # The official AdaFace repository provides PyTorch models. 
    # ONNX versions are usually provided by the community or converted manually.
    # Replace this URL with a valid AdaFace ONNX link if this community link is unavailable.
    adaface_url = "https://huggingface.co/FaceONNX/AdaFace/resolve/main/adaface_ir50.onnx"
    
    base_dir = Path(__file__).resolve().parent.parent
    models_dir = base_dir / "models"
    dest_path = models_dir / "adaface_ir50.onnx"
    
    if not models_dir.exists():
        models_dir.mkdir(parents=True, exist_ok=True)
        
    if not dest_path.exists():
        download_model(adaface_url, dest_path)
    else:
        print(f"Model already exists at {dest_path}")
