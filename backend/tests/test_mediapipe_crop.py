import cv2
import urllib.request
import numpy as np
import time

def main():
    # Download a test face
    url = "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg"
    req = urllib.request.urlopen(url)
    arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
    img = cv2.imdecode(arr, -1)
    
    # 1. Initialize FaceLandmarker
    import mediapipe as mp
    BaseOptions = mp.tasks.BaseOptions
    FaceLandmarker = mp.tasks.vision.FaceLandmarker
    FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path='app/core/face_landmarker.task'),
        running_mode=VisionRunningMode.VIDEO,
        num_faces=5,
        min_face_detection_confidence=0.1, # Lowest possible
        min_tracking_confidence=0.1,
    )
    
    try:
        landmarker = FaceLandmarker.create_from_options(options)
    except Exception as e:
        print("Model file not found here:", e)
        return

    # Test full image
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    res1 = landmarker.detect_for_video(mp_img, int(time.time() * 1000))
    print("Full image faces:", len(res1.face_landmarks) if res1 else 0)

    # Crop tightly around face (approximate)
    # Lena's face is roughly around y:220-380, x:220-380
    crop = img[220:380, 220:380]
    mp_crop = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    res2 = landmarker.detect_for_video(mp_crop, int(time.time() * 1000) + 100)
    print("Cropped image faces:", len(res2.face_landmarks) if res2 else 0)

if __name__ == "__main__":
    main()
