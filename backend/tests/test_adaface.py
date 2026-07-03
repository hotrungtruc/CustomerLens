import sys
from pathlib import Path
import cv2
from app.core.insight_embedding import InsightEmbedder

def main():
    model_path = Path(r"c:\SCHOOL\HK253\BigData\face-recognition-system\backend\models\adaface_ir18.onnx")
    if not model_path.exists():
        print(f"Model not found at {model_path}")
        return

    # Initialize embedder
    print(f"Initializing InsightEmbedder with model: {model_path.name}")
    embedder = InsightEmbedder(recognizer_path=model_path)

    image_path = Path(r"c:\SCHOOL\HK253\BigData\face-recognition-system\backend\data\images\000.jpg")
    if not image_path.exists():
        print(f"Test image not found at {image_path}")
        return

    print(f"Loading image from {image_path.name}")
    image = cv2.imread(str(image_path))
    if image is None:
        print("Failed to read image")
        return

    print("Detecting face and extracting embedding...")
    faces = embedder.get_faces(image)
    
    if not faces:
        print("No faces detected in the image.")
        return

    print(f"Detected {len(faces)} face(s).")
    for i, face in enumerate(faces):
        bbox = face['bbox']
        score = face['score']
        embedding = face['embedding']
        print(f"Face {i+1}:")
        print(f"  BBox: {bbox}")
        print(f"  Score: {score:.4f}")
        print(f"  Embedding shape: {embedding.shape}")
        print(f"  Embedding vector (first 5 values): {embedding[:5]}")

if __name__ == "__main__":
    main()
