import os
import sys
import pickle
import numpy as np
import cv2
import cvzone
import sqlite3
from datetime import datetime

# ✅ Add src to path so we can import local modules
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from insight_embedding import InsightEmbedder, SIMILARITY_THRESHOLD, cosine_similarities

# ✅ FIX: Get the project root directory (one level up from src/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ✅ Set working directory to project root
os.chdir(PROJECT_ROOT)

# ✅ Use absolute paths for all resources
DB_PATH = os.path.join(PROJECT_ROOT, "face_attendance.db")


def ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            major TEXT NOT NULL,
            starting_year INTEGER NOT NULL,
            total_attendance INTEGER NOT NULL,
            standing TEXT NOT NULL,
            year INTEGER NOT NULL,
            last_attendance_time TEXT NOT NULL
        )
        """
    )
    conn.commit()


def get_student(conn, student_id):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, major, starting_year, total_attendance, standing, year, last_attendance_time
        FROM students
        WHERE id = ?
        """,
        (student_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    keys = [
        "id",
        "name",
        "major",
        "starting_year",
        "total_attendance",
        "standing",
        "year",
        "last_attendance_time",
    ]
    return dict(zip(keys, row))


def update_attendance(conn, student_id, total_attendance, last_attendance_time):
    conn.execute(
        """
        UPDATE students
        SET total_attendance = ?, last_attendance_time = ?
        WHERE id = ?
        """,
        (total_attendance, last_attendance_time, student_id),
    )
    conn.commit()


def load_student_image(student_id):
    for extension in (".png", ".jpg", ".jpeg"):
        # ✅ Use absolute path for Images directory
        image_path = os.path.join(PROJECT_ROOT, "Images", f"{student_id}{extension}")
        if os.path.exists(image_path):
            return cv2.imread(image_path)
    return None


cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

conn = sqlite3.connect(DB_PATH)
ensure_schema(conn)

# ✅ Use absolute paths for Resources
imgBackground = cv2.imread(os.path.join(PROJECT_ROOT, "Resources", "background.png"))

# Importing the mode images into a list
folderModePath = os.path.join(PROJECT_ROOT, "Resources", "Modes")
if not os.path.isdir(folderModePath):
    folderModePath = os.path.join(PROJECT_ROOT, "Resources", "Models")
modePathList = sorted(os.listdir(folderModePath), key=lambda name: int(os.path.splitext(name)[0]))
imgModeList = []
for path in modePathList:
    imgModeList.append(cv2.imread(os.path.join(folderModePath, path)))
# print(len(imgModeList))

# Load the encoding file
print("Loading Encode File ...")
# ✅ Use absolute path for EncodeFile.p
encode_file_path = os.path.join(PROJECT_ROOT, "EncodeFile.p")
file = open(encode_file_path, "rb")
encodeListKnownWithIds = pickle.load(file)
file.close()
encodeListKnown, studentIds = encodeListKnownWithIds
# print(studentIds)
print("Encode File Loaded")
embedder = InsightEmbedder()
print(f"ONNX providers: {embedder.providers}")

modeType = 0
counter = 0
id = -1
imgStudent = []

while True:
    success, img = cap.read()

    faces = embedder.get_faces(img)

    imgBackground[162 : 162 + 480, 55 : 55 + 640] = img
    imgBackground[44 : 44 + 633, 808 : 808 + 414] = imgModeList[modeType]

    if faces:
        for face in faces:
            similarities = cosine_similarities(encodeListKnown, face["embedding"])
            if len(similarities) == 0:
                continue
            matchIndex = np.argmax(similarities)
            # print("Match Index", matchIndex)

            if similarities[matchIndex] >= SIMILARITY_THRESHOLD:
                # print("Known Face Detected")
                # print(studentIds[matchIndex])
                x1, y1, x2, y2 = face["bbox"]
                bbox = 55 + x1, 162 + y1, x2 - x1, y2 - y1
                imgBackground = cvzone.cornerRect(imgBackground, bbox, rt=0)
                id = studentIds[matchIndex]
                if counter == 0:
                    cvzone.putTextRect(imgBackground, "Loading", (275, 400))
                    cv2.imshow("Face Attendance", imgBackground)
                    cv2.waitKey(1)
                    counter = 1
                    modeType = 1

        if counter != 0:
            if counter == 1:
                # Get the Data
                studentInfo = get_student(conn, id)
                print(studentInfo)
                if not studentInfo:
                    modeType = 0
                    counter = 0
                    continue
                # Load the image from local storage
                imgStudent = load_student_image(id)
                if imgStudent is None:
                    imgStudent = np.zeros((216, 216, 3), dtype=np.uint8)
                else:
                    imgStudent = cv2.resize(imgStudent, (216, 216))
                # Update data of attendance
                try:
                    datetimeObject = datetime.strptime(
                        studentInfo["last_attendance_time"],
                        "%Y-%m-%d %H:%M:%S",
                    )
                except (TypeError, ValueError):
                    datetimeObject = datetime.min
                secondsElapsed = (datetime.now() - datetimeObject).total_seconds()
                print(secondsElapsed)
                if secondsElapsed > 30:
                    studentInfo["total_attendance"] += 1
                    update_attendance(
                        conn,
                        id,
                        studentInfo["total_attendance"],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                else:
                    modeType = 3
                    counter = 0
                    imgBackground[44 : 44 + 633, 808 : 808 + 414] = imgModeList[
                        modeType
                    ]

            if modeType != 3:
                if 10 < counter < 20:
                    modeType = 2

                imgBackground[44 : 44 + 633, 808 : 808 + 414] = imgModeList[modeType]

                if counter <= 10:
                    cv2.putText(
                        imgBackground,
                        str(studentInfo["total_attendance"]),
                        (861, 125),
                        cv2.FONT_HERSHEY_COMPLEX,
                        1,
                        (255, 255, 255),
                        1,
                    )
                    cv2.putText(
                        imgBackground,
                        str(studentInfo["major"]),
                        (1006, 550),
                        cv2.FONT_HERSHEY_COMPLEX,
                        0.5,
                        (255, 255, 255),
                        1,
                    )
                    cv2.putText(
                        imgBackground,
                        str(id),
                        (1006, 493),
                        cv2.FONT_HERSHEY_COMPLEX,
                        0.5,
                        (255, 255, 255),
                        1,
                    )
                    cv2.putText(
                        imgBackground,
                        str(studentInfo["standing"]),
                        (910, 625),
                        cv2.FONT_HERSHEY_COMPLEX,
                        0.6,
                        (100, 100, 100),
                        1,
                    )
                    cv2.putText(
                        imgBackground,
                        str(studentInfo["year"]),
                        (1025, 625),
                        cv2.FONT_HERSHEY_COMPLEX,
                        0.6,
                        (100, 100, 100),
                        1,
                    )
                    cv2.putText(
                        imgBackground,
                        str(studentInfo["starting_year"]),
                        (1125, 625),
                        cv2.FONT_HERSHEY_COMPLEX,
                        0.6,
                        (100, 100, 100),
                        1,
                    )

                    (w, h), _ = cv2.getTextSize(
                        studentInfo["name"], cv2.FONT_HERSHEY_COMPLEX, 1, 1
                    )
                    offset = (414 - w) // 2
                    cv2.putText(
                        imgBackground,
                        str(studentInfo["name"]),
                        (808 + offset, 445),
                        cv2.FONT_HERSHEY_COMPLEX,
                        1,
                        (50, 50, 50),
                        1,
                    )

                    imgBackground[175 : 175 + 216, 909 : 909 + 216] = imgStudent

                counter += 1

                if counter >= 20:
                    counter = 0
                    modeType = 0
                    studentInfo = []
                    imgStudent = []
                    imgBackground[44 : 44 + 633, 808 : 808 + 414] = imgModeList[
                        modeType
                    ]
    else:
        modeType = 0
        counter = 0
    # cv2.imshow("Webcam", img)
    cv2.imshow("Face Attendance", imgBackground)
    cv2.waitKey(1)
