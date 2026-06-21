import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";

let faceDetector = null;

/**
 * Initialize MediaPipe FaceDetector
 * Runs on GPU if available, falls back to CPU
 */
export async function initFaceDetector() {
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm",
  );

  faceDetector = await FaceDetector.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath:
        "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    minDetectionConfidence: 0.6,
    minSuppressionThreshold: 0.3,
  });

  console.log("✓ FaceDetector ready");
  return faceDetector;
}

export function getDetector() {
  return faceDetector;
}

export function isDetectorReady() {
  return faceDetector !== null;
}
