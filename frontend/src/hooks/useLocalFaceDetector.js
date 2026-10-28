"use client";

import { useEffect, useState, useRef } from "react";
import { initSCRFD, detectFacesSCRFD } from "../lib/scrfdDetector";
import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";

const MAX_LOST_FRAMES = 22; // Coast tracks for ~700ms when detector misses a frame (prevents ID fragmentation)
const EMA_ALPHA = 0.65; // Smoothing factor for bounding box coordinates
const DET_CONFIDENCE = 0.58; // Confidence threshold for MediaPipe / SCRFD (clean noise rejection)
const MIN_BBOX_SIZE = 32; // Minimum face pixel dimension (rejects noise < 32px)

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
  const detectorModeRef = useRef("none"); // "mediapipe" | "scrfd" | "none"
  const mediapipeDetectorRef = useRef(null);
  const requestRef = useRef(null);
  const lastVideoTimeRef = useRef(-1);
  const trackedFacesRef = useRef([]);
  const isDetectingRef = useRef(false);

  useEffect(() => {
    let isMounted = true;

    async function initDetector() {
      // 1. Try MediaPipe FaceDetector first (BlazeFace 60 FPS Edge Detector)
      try {
        const vision = await FilesetResolver.forVisionTasks(
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm"
        );

        let detector = null;
        // Priority A: BlazeFace Full-Range with GPU delegate
        try {
          detector = await FaceDetector.createFromOptions(vision, {
            baseOptions: {
              modelAssetPath: "/models/blaze_face_full_range.tflite",
              delegate: "GPU",
            },
            runningMode: "VIDEO",
            minDetectionConfidence: DET_CONFIDENCE,
          });
        } catch (gpuFullErr) {
          console.warn("MediaPipe Full-Range GPU failed, trying Short-Range GPU:", gpuFullErr);
          try {
            detector = await FaceDetector.createFromOptions(vision, {
              baseOptions: {
                modelAssetPath: "/models/blaze_face_short_range.tflite",
                delegate: "GPU",
              },
              runningMode: "VIDEO",
              minDetectionConfidence: DET_CONFIDENCE,
            });
          } catch (gpuShortErr) {
            console.warn("GPU delegate failed, trying CPU delegate:", gpuShortErr);
            detector = await FaceDetector.createFromOptions(vision, {
              baseOptions: {
                modelAssetPath: "/models/blaze_face_full_range.tflite",
                delegate: "CPU",
              },
              runningMode: "VIDEO",
              minDetectionConfidence: DET_CONFIDENCE,
            });
          }
        }

        if (detector && isMounted) {
          mediapipeDetectorRef.current = detector;
          detectorModeRef.current = "mediapipe";
          console.log("✓ MediaPipe FaceDetector (BlazeFace) initialized as primary Edge Detector");
          return;
        }
      } catch (mpErr) {
        console.warn("MediaPipe FaceDetector init failed, falling back to SCRFD ONNX:", mpErr);
      }

      // 2. Fallback to SCRFD ONNX Detector if MediaPipe cannot be initialized
      try {
        await initSCRFD("/models/scrfd_500m_bnkps.onnx");
        if (isMounted) {
          detectorModeRef.current = "scrfd";
          console.log("✓ Edge SCRFD (ONNX Runtime Web) face detector ready as fallback");
        }
      } catch (scrfdErr) {
        console.error("Failed to initialize any face detector:", scrfdErr);
      }
    }

    initDetector();

    return () => {
      isMounted = false;
      if (mediapipeDetectorRef.current) {
        try {
          mediapipeDetectorRef.current.close();
        } catch (_) {}
      }
    };
  }, []);

  useEffect(() => {
    async function detectFaces() {
      const video = videoRef.current;
      if (
        detectorModeRef.current !== "none" &&
        video &&
        video.readyState >= 2 &&
        !isDetectingRef.current
      ) {
        if (lastVideoTimeRef.current !== video.currentTime) {
          lastVideoTimeRef.current = video.currentTime;
          isDetectingRef.current = true;

          try {
            const sw = video.videoWidth;
            const sh = video.videoHeight;
            let mappedFaces = [];

            if (detectorModeRef.current === "mediapipe" && mediapipeDetectorRef.current) {
              // --- MediaPipe FaceDetector (BlazeFace) Execution ---
              const startTimeMs = performance.now();
              const results = mediapipeDetectorRef.current.detectForVideo(video, startTimeMs);

              if (results && results.detections && results.detections.length > 0) {
                mappedFaces = results.detections
                  .filter((d) => {
                    if (!d.boundingBox) return false;
                    const { originX = 0, originY = 0, width, height } = d.boundingBox;
                    if (width < MIN_BBOX_SIZE || height < MIN_BBOX_SIZE) return false;
                    if (width > sw * 0.7 || height > sh * 0.7) return false;

                    // 1. Aspect ratio check (human face is vertical/square: 0.72 - 1.65)
                    const ar = height / Math.max(1, width);
                    if (ar < 0.72 || ar > 1.65) return false;

                    // 2. Score threshold check
                    const score = d.categories?.[0]?.score ?? 0.5;
                    if (score < DET_CONFIDENCE) return false;

                    // 3. MediaPipe 6 keypoints geometry verification
                    // 0: Right Eye, 1: Left Eye, 2: Nose Tip, 3: Mouth Center, 4: Right Ear, 5: Left Ear
                    const kps = d.keypoints;
                    if (!kps || kps.length < 4) return false;

                    const rEye = kps[0];
                    const lEye = kps[1];
                    const nose = kps[2];
                    const mouth = kps[3];
                    if (!rEye || !lEye || !nose || !mouth) return false;

                    // Ensure keypoints fall strictly inside the normalized bounding box
                    const boxLeftNorm = originX / sw;
                    const boxRightNorm = (originX + width) / sw;
                    const boxTopNorm = originY / sh;
                    const boxBottomNorm = (originY + height) / sh;

                    for (let i = 0; i < 4; i++) {
                      const pt = kps[i];
                      if (
                        pt.x < boxLeftNorm - 0.03 ||
                        pt.x > boxRightNorm + 0.03 ||
                        pt.y < boxTopNorm - 0.03 ||
                        pt.y > boxBottomNorm + 0.03
                      ) {
                        return false;
                      }
                    }

                    // Both eyes must be higher than the mouth
                    if (rEye.y >= mouth.y || lEye.y >= mouth.y) return false;

                    // Minimum eye distance relative to face size (rejects ears, profile, noise)
                    const eyeDistNorm = Math.hypot(lEye.x - rEye.x, lEye.y - rEye.y);
                    const faceWidthNorm = width / sw;
                    if (eyeDistNorm / Math.max(0.01, faceWidthNorm) < 0.18) return false;

                    // Nose tip must be vertically between eyes and mouth
                    const eyeYMin = Math.min(rEye.y, lEye.y) - 0.03;
                    const mouthYMax = mouth.y + 0.03;
                    if (nose.y < eyeYMin || nose.y > mouthYMax) return false;

                    return true;
                  })
                  .map((d) => {
                    const bbox = d.boundingBox;
                    const originX = Math.max(0, bbox.originX);
                    const originY = Math.max(0, bbox.originY);
                    const width = Math.min(sw - originX, bbox.width);
                    const height = Math.min(sh - originY, bbox.height);
                    const score = d.categories?.[0]?.score || 0.5;

                    return {
                      left: (originX / sw) * 100,
                      top: (originY / sh) * 100,
                      width: (width / sw) * 100,
                      height: (height / sh) * 100,
                      pixelBox: { originX, originY, width, height },
                      keypoints: d.keypoints || [],
                      score,
                      isGoodQuality: width >= 32 && height >= 32 && score >= 0.55,
                    };
                  });
              }
            } else if (detectorModeRef.current === "scrfd") {
              // --- SCRFD ONNX Fallback Detection ---
              const scrfdResults = await detectFacesSCRFD(video, DET_CONFIDENCE);
              mappedFaces = scrfdResults
                .filter((f) => {
                  if (f.width < MIN_BBOX_SIZE || f.height < MIN_BBOX_SIZE) return false;
                  const ar = f.height / Math.max(1, f.width);
                  if (ar < 0.72 || ar > 1.65) return false;
                  if (f.score < DET_CONFIDENCE) return false;
                  // Geometric verification on 5 facial keypoints: eyes above mouth
                  if (f.keypoints && f.keypoints.length >= 4) {
                    const avgEyeY = (f.keypoints[0].py + f.keypoints[1].py) / 2;
                    const avgMouthY = (f.keypoints[3].py + (f.keypoints[4]?.py ?? f.keypoints[3].py)) / 2;
                    if (avgMouthY <= avgEyeY) return false;
                  }
                  return true;
                })
                .map((f) => {
                  const originX = f.x1;
                  const originY = f.y1;
                  const width = f.width;
                  const height = f.height;
                  const isGoodQuality = width >= 32 && height >= 32 && f.score >= 0.55;

                  return {
                    left: (originX / sw) * 100,
                    top: (originY / sh) * 100,
                    width: (width / sw) * 100,
                    height: (height / sh) * 100,
                    pixelBox: { originX, originY, width, height },
                    keypoints: f.keypoints,
                    score: f.score,
                    isGoodQuality,
                  };
                });
            }

            // --- Robust Multi-Object Tracking & Motion Smoothing ---
            const existingTracks = trackedFacesRef.current;
            const updatedTracks = [];
            const matchedTrackIndices = new Set();
            const matchedDetectionIndices = new Set();

            // 1. Predict track position forward using linear velocity
            const predictedTracks = existingTracks.map((track) => ({
              ...track,
              predLeft: track.left + (track.vx || 0),
              predTop: track.top + (track.vy || 0),
            }));

            // 2. Greedy association using IoU + Centroid distance fallback
            mappedFaces.forEach((face, detIdx) => {
              let bestScore = -1;
              let bestTrackIdx = -1;

              predictedTracks.forEach((track, trkIdx) => {
                if (matchedTrackIndices.has(trkIdx)) return;

                const predBox = {
                  left: track.predLeft,
                  top: track.predTop,
                  width: track.width,
                  height: track.height,
                };

                const iouPred = calculateIoU(face, predBox);
                const iouDirect = calculateIoU(face, track);
                const iou = Math.max(iouPred, iouDirect);

                // Normalized centroid distance
                const fcx = face.left + face.width / 2;
                const fcy = face.top + face.height / 2;
                const tcx = predBox.left + predBox.width / 2;
                const tcy = predBox.top + predBox.height / 2;
                const dist = Math.hypot(fcx - tcx, fcy - tcy);
                const diag = Math.hypot(face.width, face.height);
                const normDist = dist / (diag || 1);

                // Valid match criteria: IoU >= 0.18 OR close centroid distance
                const isMatch = iou >= 0.18 || (iou >= 0.06 && normDist < 0.5) || normDist < 0.3;

                if (isMatch) {
                  const matchScore = iou * 2.0 - normDist;
                  if (matchScore > bestScore) {
                    bestScore = matchScore;
                    bestTrackIdx = trkIdx;
                  }
                }
              });

              if (bestTrackIdx >= 0) {
                matchedTrackIndices.add(bestTrackIdx);
                matchedDetectionIndices.add(detIdx);

                const prevTrack = existingTracks[bestTrackIdx];

                // Calculate instantaneous velocity & smooth it
                const rawVx = face.left - prevTrack.left;
                const rawVy = face.top - prevTrack.top;
                const smoothVx = (prevTrack.vx || 0) * 0.35 + rawVx * 0.65;
                const smoothVy = (prevTrack.vy || 0) * 0.35 + rawVy * 0.65;

                // EMA coordinate smoothing to eliminate jitter while following fast motion
                const smoothLeft = prevTrack.left * (1 - EMA_ALPHA) + face.left * EMA_ALPHA;
                const smoothTop = prevTrack.top * (1 - EMA_ALPHA) + face.top * EMA_ALPHA;
                const smoothWidth = prevTrack.width * (1 - EMA_ALPHA) + face.width * EMA_ALPHA;
                const smoothHeight = prevTrack.height * (1 - EMA_ALPHA) + face.height * EMA_ALPHA;

                updatedTracks.push({
                  ...face,
                  left: smoothLeft,
                  top: smoothTop,
                  width: smoothWidth,
                  height: smoothHeight,
                  vx: smoothVx,
                  vy: smoothVy,
                  local_track_id: prevTrack.local_track_id,
                  first_seen: prevTrack.first_seen,
                  lost_frames: 0,
                  hit_streak: (prevTrack.hit_streak || 0) + 1,
                  isCoasting: false,
                });
              }
            });

            // 3. Register brand new tracks for unmatched detections (only if not overlapping an existing track)
            mappedFaces.forEach((face, detIdx) => {
              if (!matchedDetectionIndices.has(detIdx)) {
                // Ensure this unmatched detection does not heavily overlap an already updated track
                const overlapsExisting = updatedTracks.some(
                  (t) => calculateIoU(face, t) > 0.25
                );
                if (!overlapsExisting) {
                  updatedTracks.push({
                    ...face,
                    vx: 0,
                    vy: 0,
                    local_track_id: "local_" + generateUUID(),
                    first_seen: Date.now(),
                    lost_frames: 0,
                    hit_streak: 1,
                    isCoasting: false,
                  });
                }
              }
            });

            // 4. Coasting Buffer: preserve existing tracks missed in this frame for up to MAX_LOST_FRAMES
            existingTracks.forEach((track, trkIdx) => {
              if (!matchedTrackIndices.has(trkIdx)) {
                const lostFrames = (track.lost_frames || 0) + 1;
                if (lostFrames <= MAX_LOST_FRAMES) {
                  // Coast position using decaying velocity
                  const coastingLeft = track.left + (track.vx || 0) * 0.6;
                  const coastingTop = track.top + (track.vy || 0) * 0.6;

                  updatedTracks.push({
                    ...track,
                    left: coastingLeft,
                    top: coastingTop,
                    vx: (track.vx || 0) * 0.8,
                    vy: (track.vy || 0) * 0.8,
                    lost_frames: lostFrames,
                    isCoasting: true,
                  });
                }
              }
            });

            // 5. Track-to-Track De-duplication (Suppression)
            // Sort by hit_streak descending so stronger, older tracks suppress weaker ghosts
            const deduplicatedTracks = [];
            updatedTracks.sort((a, b) => (b.hit_streak || 0) - (a.hit_streak || 0));

            for (let i = 0; i < updatedTracks.length; i++) {
              const a = updatedTracks[i];
              let isDuplicate = false;
              for (let j = 0; j < deduplicatedTracks.length; j++) {
                const b = deduplicatedTracks[j];
                const iou = calculateIoU(a, b);
                if (iou > 0.3) {
                  isDuplicate = true;
                  break;
                }
              }
              if (!isDuplicate) {
                deduplicatedTracks.push(a);
              }
            }

            trackedFacesRef.current = deduplicatedTracks;

            // Render visible tracks: only display active tracks with at least 2 consistent detection hits
            const renderableFaces = deduplicatedTracks.filter(
              (t) => (t.hit_streak >= 2) && (!t.isCoasting || t.lost_frames <= 2)
            );
            setLocalFaces(renderableFaces);
          } catch (err) {
            console.error("Face detection loop error:", err);
          } finally {
            isDetectingRef.current = false;
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
