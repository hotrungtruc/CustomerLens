import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

let faceLandmarker = null;

/**
 * Initialize MediaPipe FaceLandmarker Tasks API (face_landmarker.task)
 * Runs on GPU if available, falls back to CPU
 */
export async function initFaceDetector() {
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm",
  );

  try {
    faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: "/models/face_landmarker.task",
        delegate: "GPU",
      },
      runningMode: "VIDEO",
      numFaces: 5,
      minFaceDetectionConfidence: 0.4,
      minFacePresenceConfidence: 0.4,
      outputFaceBlendshapes: false,
      outputFacialTransformationMatrixes: false,
    });
  } catch (err) {
    console.warn("GPU init failed, falling back to CPU for FaceLandmarker:", err);
    faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        delegate: "CPU",
      },
      runningMode: "VIDEO",
      numFaces: 5,
      minFaceDetectionConfidence: 0.4,
      minFacePresenceConfidence: 0.4,
      outputFaceBlendshapes: false,
      outputFacialTransformationMatrixes: false,
    });
  }

  console.log("✓ MediaPipe FaceLandmarker Tasks API ready");
  return faceLandmarker;
}

export function getDetector() {
  return faceLandmarker;
}

export function isDetectorReady() {
  return faceLandmarker !== null;
}
