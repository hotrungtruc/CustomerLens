"use client";

import { useEffect, useState, useRef } from "react";
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

function calculateIoU(boxA, boxB) {
  const xA = Math.max(boxA.left, boxB.left);
  const yA = Math.max(boxA.top, boxB.top);
  const xB = Math.min(boxA.left + boxA.width, boxB.left + boxB.width);
  const yB = Math.min(boxA.top + boxA.height, boxB.top + boxB.height);
  const interArea = Math.max(0, xB - xA) * Math.max(0, yB - yA);
  if (interArea === 0) return 0;
  const boxAArea = boxA.width * boxA.height;
  const boxBArea = boxB.width * boxB.height;
  return interArea / (boxAArea + boxBArea - interArea);
}

function generateUUID() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16),
  );
}

export function useLocalFaceDetector(videoRef) {
  const [localFaces, setLocalFaces] = useState([]);
  const faceDetectorRef = useRef(null);
  const requestRef = useRef(null);
  const lastVideoTimeRef = useRef(-1);
  const trackedFacesRef = useRef([]);

  useEffect(() => {
    let isMounted = true;

    async function initDetector() {
      try {
        const vision = await FilesetResolver.forVisionTasks(
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm",
        );

        const REMOTE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
        const LOCAL_MODEL_URL = "/models/face_landmarker.task";

        let faceLandmarker = null;
        try {
          // Priority 1: Load local face_landmarker.task with GPU
          faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
            baseOptions: {
              modelAssetPath: LOCAL_MODEL_URL,
              delegate: "GPU",
            },
            runningMode: "VIDEO",
            numFaces: 5,
            minFaceDetectionConfidence: 0.35,
            minFacePresenceConfidence: 0.35,
          });
        } catch (localGpuErr) {
          console.warn("Local GPU init failed, trying Remote CDN with GPU:", localGpuErr);
          try {
            // Priority 2: Remote Google Cloud CDN with GPU
            faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
              baseOptions: {
                modelAssetPath: REMOTE_MODEL_URL,
                delegate: "GPU",
              },
              runningMode: "VIDEO",
              numFaces: 5,
              minFaceDetectionConfidence: 0.35,
              minFacePresenceConfidence: 0.35,
            });
          } catch (remoteGpuErr) {
            console.warn("Remote GPU failed, trying CPU fallback:", remoteGpuErr);
            // Priority 3: CPU fallback
            faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
              baseOptions: {
                modelAssetPath: REMOTE_MODEL_URL,
                delegate: "CPU",
              },
              runningMode: "VIDEO",
              numFaces: 5,
              minFaceDetectionConfidence: 0.35,
              minFacePresenceConfidence: 0.35,
            });
          }
        }

        if (isMounted) {
          faceDetectorRef.current = faceLandmarker;
          console.log("✓ MediaPipe FaceLandmarker Tasks API initialized on edge web client");
        }
      } catch (err) {
        console.error("Failed to initialize MediaPipe FaceLandmarker:", err);
      }
    }

    initDetector();

    return () => {
      isMounted = false;
      if (faceDetectorRef.current) {
        try {
          faceDetectorRef.current.close();
        } catch (_) {}
      }
    };
  }, []);

  useEffect(() => {
    function detectFaces() {
      if (faceDetectorRef.current && videoRef.current && videoRef.current.readyState >= 2) {
        const startTimeMs = performance.now();
        const video = videoRef.current;

        // Only run detection if the video frame has advanced
        if (lastVideoTimeRef.current !== video.currentTime) {
          lastVideoTimeRef.current = video.currentTime;

          try {
            const results = faceDetectorRef.current.detectForVideo(video, startTimeMs);
            if (results && results.faceLandmarks && results.faceLandmarks.length > 0) {
              const sw = video.videoWidth;
              const sh = video.videoHeight;

              const mappedFaces = results.faceLandmarks.map((landmarks) => {
                let minX = 1.0, minY = 1.0, maxX = 0.0, maxY = 0.0;
                for (let i = 0; i < landmarks.length; i++) {
                  const pt = landmarks[i];
                  if (pt.x < minX) minX = pt.x;
                  if (pt.x > maxX) maxX = pt.x;
                  if (pt.y < minY) minY = pt.y;
                  if (pt.y > maxY) maxY = pt.y;
                }

                const rawW = (maxX - minX) * sw;
                const rawH = (maxY - minY) * sh;
                const mx = rawW * 0.06;
                const my = rawH * 0.06;

                const originX = Math.max(0, minX * sw - mx);
                const originY = Math.max(0, minY * sh - my);
                const width = Math.min(sw - originX, rawW + mx * 2);
                const height = Math.min(sh - originY, rawH + my * 2);

                // Margin check (touching borders)
                const marginX = sw * 0.04;
                const marginY = sh * 0.04;
                const isAtEdge =
                  originX < marginX ||
                  originY < marginY ||
                  originX + width > sw - marginX ||
                  originY + height > sh - marginY;

                // Extract Key Reference Points
                // 468/33: Left Eye, 473/263: Right Eye, 1: Nose Tip, 61: Left Mouth, 291: Right Mouth
                const leftEye = landmarks[468] || landmarks[33] || landmarks[133];
                const rightEye = landmarks[473] || landmarks[263] || landmarks[362];
                const nose = landmarks[1];
                const mouthL = landmarks[61];
                const mouthR = landmarks[291];

                const mouthCenter = (mouthL && mouthR)
                  ? { x: (mouthL.x + mouthR.x) / 2.0, y: (mouthL.y + mouthR.y) / 2.0 }
                  : (mouthL || nose);

                const keypoints = [leftEye, rightEye, nose, mouthCenter];

                // Pose Gate: Yaw and Eye Distance Symmetry
                let isExtremeProfile = false;
                let isEyesWideEnough = true;

                if (leftEye && rightEye && nose) {
                  const distRight = Math.sqrt(Math.pow((rightEye.x - nose.x) * sw, 2) + Math.pow((rightEye.y - nose.y) * sh, 2));
                  const distLeft = Math.sqrt(Math.pow((leftEye.x - nose.x) * sw, 2) + Math.pow((leftEye.y - nose.y) * sh, 2));
                  const eyeDist = Math.sqrt(Math.pow((rightEye.x - leftEye.x) * sw, 2) + Math.pow((rightEye.y - leftEye.y) * sh, 2));
                  const ratio = distRight > 0 ? distLeft / distRight : 999;

                  if (ratio > 1.85 || ratio < 0.54) {
                    isExtremeProfile = true;
                  }

                  const minEyeRatio = width < 60 ? 0.16 : 0.20;
                  if (eyeDist < width * minEyeRatio) {
                    isEyesWideEnough = false;
                  }
                }

                const isGoodQuality = !isAtEdge && !isExtremeProfile && isEyesWideEnough && width >= 28 && height >= 28;

                return {
                  left: (originX / sw) * 100,
                  top: (originY / sh) * 100,
                  width: (width / sw) * 100,
                  height: (height / sh) * 100,
                  pixelBox: { originX, originY, width, height },
                  keypoints,
                  isGoodQuality,
                };
              });

              // Tracking Association (IoU matching)
              const currentTracks = trackedFacesRef.current;
              const newTracks = [];

              mappedFaces.forEach((face) => {
                let bestMatch = null;
                let bestIoU = 0;
                currentTracks.forEach((track) => {
                  if (track.matched) return;
                  const iou = calculateIoU(face, track);
                  if (iou > 0.3 && iou > bestIoU) {
                    bestIoU = iou;
                    bestMatch = track;
                  }
                });

                if (bestMatch) {
                  bestMatch.matched = true;
                  newTracks.push({
                    ...face,
                    local_track_id: bestMatch.local_track_id,
                    first_seen: bestMatch.first_seen,
                  });
                } else {
                  newTracks.push({
                    ...face,
                    local_track_id: "local_" + generateUUID(),
                    first_seen: Date.now(),
                  });
                }
              });

              trackedFacesRef.current = newTracks;
              setLocalFaces(newTracks);
            } else {
              trackedFacesRef.current = [];
              setLocalFaces([]);
            }
          } catch (err) {
            console.error("FaceLandmarker detection error:", err);
          }
        }
      }

      requestRef.current = requestAnimationFrame(detectFaces);
    }

    requestRef.current = requestAnimationFrame(detectFaces);
    return () => {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    };
  }, [videoRef]);

  return localFaces;
}
