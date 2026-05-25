import cv2
import pickle
import os
import sys

# ✅ Add src to path so we can import local modules
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from insight_embedding import InsightEmbedder

# ✅ FIX: Get the project root directory (one level up from src/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ✅ Set working directory to project root
os.chdir(PROJECT_ROOT)

# Importing student images
# ✅ Use absolute path for Images directory
folderPath = os.path.join(PROJECT_ROOT, "Images")
pathList = os.listdir(folderPath)
print(pathList)
imgList = []
studentIds = []
for path in pathList:
    imgList.append(cv2.imread(os.path.join(folderPath, path)))
    studentIds.append(os.path.splitext(path)[0])

    # print(path)
    # print(os.path.splitext(path)[0])
print(studentIds)


def findEncodings(imagesList):
    embedder = InsightEmbedder()
    encodeList = []
    for img in imagesList:
        faces = embedder.get_faces(img)
        if not faces:
            raise ValueError("No face found in one of the source images.")
        encode = faces[0]["embedding"]
        encodeList.append(encode)

    return encodeList


print("Encoding Started ...")
encodeListKnown = findEncodings(imgList)
encodeListKnownWithIds = [encodeListKnown, studentIds]
print("Encoding Complete")

# ✅ Use absolute path for EncodeFile.p
encode_file_path = os.path.join(PROJECT_ROOT, "EncodeFile.p")
file = open(encode_file_path, "wb")
pickle.dump(encodeListKnownWithIds, file)
file.close()
print("File Saved")
