"use client";

import { useEffect, useState, useRef } from "react";
import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";

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
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, c =>
    (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
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
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm"
        );
        const faceDetector = await FaceDetector.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
            delegate: "GPU",
          },
          runningMode: "VIDEO",
        });

        if (isMounted) {
          faceDetectorRef.current = faceDetector;
        }
      } catch (err) {
        console.error("Failed to initialize MediaPipe FaceDetector:", err);
      }
    }
    
    initDetector();
    
    return () => {
      isMounted = false;
      if (faceDetectorRef.current) {
        faceDetectorRef.current.close();
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
             const detections = faceDetectorRef.current.detectForVideo(video, startTimeMs);
             if (detections && detections.detections) {
                 const sw = video.videoWidth;
                 const sh = video.videoHeight;
                 
                 const mappedFaces = detections.detections.map(d => {
                     const { originX, originY, width, height } = d.boundingBox;
                     return {
                         left: (originX / sw) * 100,
                         top: (originY / sh) * 100,
                         width: (width / sw) * 100,
                         height: (height / sh) * 100,
                         pixelBox: { originX, originY, width, height },
                         keypoints: d.keypoints || []
                     };
                 });

                 // IoU Tracking
                 const currentTracks = trackedFacesRef.current;
                 const newTracks = [];

                 mappedFaces.forEach(face => {
                   let bestMatch = null;
                   let bestIoU = 0;
                   currentTracks.forEach(track => {
                     if (track.matched) return; // Prevent double matching
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
          } catch(err) {
             console.error("Face detection error:", err);
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
