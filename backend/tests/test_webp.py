import cv2
import numpy as np

dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
success, encoded = cv2.imencode('.webp', dummy_img)
if success:
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    print(f'WebP support: {decoded is not None}')
else:
    print('Failed to encode WebP, OpenCV might not support it')
