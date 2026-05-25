import os
import pickle

import cv2

from app.core.insight_embedding import InsightEmbedder
from config import ENCODE_FILE, IMAGES_DIR


def generate_encodings():
    if not IMAGES_DIR.exists():
        raise FileNotFoundError(f"Images directory not found: {IMAGES_DIR}")

    path_list = os.listdir(IMAGES_DIR)
    img_list = []
    customer_ids = []
    for filename in path_list:
        img_list.append(cv2.imread(str(IMAGES_DIR / filename)))
        customer_ids.append(os.path.splitext(filename)[0])

    embedder = InsightEmbedder()
    encode_list = []
    for img in img_list:
        faces = embedder.get_faces(img)
        if not faces:
            raise ValueError("No face found in one of the source images.")
        encode_list.append(faces[0]["embedding"])

    encode_list_known_with_ids = [encode_list, customer_ids]
    ENCODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ENCODE_FILE, "wb") as file:
        pickle.dump(encode_list_known_with_ids, file)


if __name__ == "__main__":
    generate_encodings()
