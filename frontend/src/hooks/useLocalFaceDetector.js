"use client";

import { useEffect, useState, useRef } from "react";
import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";

export function useLocalFaceDetector(videoRef) {
  const [localFaces, setLocalFaces] = useState([]);
  const faceDetectorRef = useRef(null);
  const requestRef = useRef(null);
  const lastVideoTimeRef = useRef(-1);

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
                     };
                 });
                 setLocalFaces(mappedFaces);
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
