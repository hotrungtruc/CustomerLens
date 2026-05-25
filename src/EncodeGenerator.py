import cv2
import pickle
import os

from insight_embedding import InsightEmbedder


# Importing student images
folderPath = "Images"
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

file = open("EncodeFile.p", "wb")
pickle.dump(encodeListKnownWithIds, file)
file.close()
print("File Saved")
