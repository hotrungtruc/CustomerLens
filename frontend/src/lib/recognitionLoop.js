import { initFaceDetector, getDetector } from "./faceDetector.js";
import { cropFaceToBlob } from "./faceCrop.js";
import { API_BASE_URL } from "../services/api.js";

const SEND_INTERVAL_MS = 800; // Debounce: send at most once per 800ms
const MIN_FACE_SIZE = 80; // Bounding box smaller than 80px = too far
const STABLE_FRAMES = 3; // Face must appear 3 consecutive frames before sending

let lastSentTime = 0;
let stableCount = 0;
let animFrameId = null;
let lastTimestamp = 0;
let isRunning = false;

/**
 * Start the main recognition loop
 * @param {HTMLVideoElement} videoEl - Video element with camera stream
 * @param {Function} onResult - Callback when recognition result received
 */
export async function startRecognitionLoop(videoEl, onResult) {
  if (isRunning) return;

  try {
    await initFaceDetector();
    isRunning = true;
    lastSentTime = 0;
    stableCount = 0;
    lastTimestamp = 0;

    console.log("✓ Recognition loop started");
    loop(videoEl, onResult);
  } catch (err) {
    console.error("Failed to start recognition loop:", err);
    throw err;
  }
}

export function stopRecognitionLoop() {
  if (animFrameId) {
    cancelAnimationFrame(animFrameId);
  }
  isRunning = false;
  lastSentTime = 0;
  stableCount = 0;
  lastTimestamp = 0;
  console.log("✓ Recognition loop stopped");
}

function loop(videoEl, onResult) {
  animFrameId = requestAnimationFrame(async (timestamp) => {
    // Only process when video is playing and new frame available
    if (videoEl.readyState >= 2 && timestamp !== lastTimestamp) {
      lastTimestamp = timestamp;

      try {
        const detector = getDetector();
        if (!detector) {
          loop(videoEl, onResult);
          return;
        }

        const detections = detector.detectForVideo(
          videoEl,
          timestamp,
        ).detections;

        if (detections.length > 0) {
          const best = getLargestFace(detections);
          const bbox = normBboxToPixels(best.boundingBox, videoEl);

          if (bbox.width >= MIN_FACE_SIZE) {
            stableCount++;

            // Send API only when: face stable + debounce interval passed
            const now = Date.now();
            if (
              stableCount >= STABLE_FRAMES &&
              now - lastSentTime > SEND_INTERVAL_MS
            ) {
              lastSentTime = now;
              stableCount = 0;

              try {
                const blob = await cropFaceToBlob(videoEl, bbox);
                const result = await sendToBackend(blob);
                onResult(result);
              } catch (err) {
                console.error("Recognition error:", err);
              }
            }
          } else {
            stableCount = 0; // Face too small / too far
          }
        } else {
          stableCount = 0; // No face detected
        }
      } catch (err) {
        console.error("Loop error:", err);
      }
    }

    if (isRunning) {
      loop(videoEl, onResult);
    }
  });
}

/**
 * Get the largest (closest) face from detections
 */
function getLargestFace(detections) {
  return detections.reduce((best, d) => {
    const bestArea = best.boundingBox.width * best.boundingBox.height;
    const dArea = d.boundingBox.width * d.boundingBox.height;
    return dArea > bestArea ? d : best;
  });
}

/**
 * Convert normalized bounding box (0–1) to pixel coordinates
 */
function normBboxToPixels(normBbox, videoEl) {
  return {
    x: normBbox.originX * videoEl.videoWidth,
    y: normBbox.originY * videoEl.videoHeight,
    width: normBbox.width * videoEl.videoWidth,
    height: normBbox.height * videoEl.videoHeight,
  };
}

/**
 * Send cropped face to backend API
 * @param {Blob} faceBlob - 112×112 JPEG image
 * @returns {Promise<Object>} Recognition result
 */
async function sendToBackend(faceBlob) {
  const formData = new FormData();
  formData.append("face", faceBlob, "face.jpg");

  const res = await fetch(`${API_BASE_URL}/api/recognize`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }

  return res.json();
}
