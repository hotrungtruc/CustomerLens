"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const CAPTURE_INTERVAL_MS = 50; // 20 fps
const JPEG_QUALITY = 0.75;
const MAX_UPLOAD_WIDTH = 640;
const MAX_UPLOAD_HEIGHT = 360;
const RECONNECT_DELAY_MS = 2000;

function getWsUrl(sessionId) {
  // Derive WS URL from the API base URL so it works in any environment
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  let host = "localhost:8000";
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_HOST;
  if (baseUrl) {
    try {
      // Handle both full URLs (http://host:port) and bare host:port
      const url = baseUrl.includes("://") ? new URL(baseUrl) : new URL(`http://${baseUrl}`);
      host = url.host; // includes port if present
    } catch (_) {
      host = baseUrl.replace(/^https?:\/\//, "");
    }
  }
  return `${protocol}//${host}/ws/${encodeURIComponent(sessionId)}`;
}

/**
 * useCamera — unified WebSocket + webcam hook.
 *
 * Replaces both useCustomerDetection (HTTP polling) and the HTTP POST loop
 * that was inside CameraStream.
 *
 * Returns:
 *   videoRef, canvasRef       — attach to <video> / <canvas>
 *   customers, frameSize      — annotation data from backend
 *   wsStatus                  — "connecting" | "live" | "error" | "disconnected"
 *   devices, selectedDeviceId, setSelectedDeviceId — camera selector
 *   cameraError               — getUserMedia error message
 */
export function useCamera(sessionId) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const wsRef = useRef(null);
  const mountedRef = useRef(true);
  const sendingRef = useRef(false);
  const reconnectRef = useRef(null);
  const skipNextDeviceStartRef = useRef(false);
  const lastSendTimeRef = useRef(0);

  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [wsStatus, setWsStatus] = useState("connecting");
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [cameraError, setCameraError] = useState("");

  // ── WebSocket lifecycle ───────────────────────────────────────────────────
  const connectWs = useCallback(() => {
    if (!mountedRef.current) return;

    const ws = new WebSocket(getWsUrl(sessionId));
    wsRef.current = ws;
    setWsStatus("connecting");

    ws.onopen = () => {
      if (mountedRef.current) setWsStatus("live");
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(event.data);
        if (data.frame_size?.width) setFrameSize(data.frame_size);
        setCustomers(data.customers ?? []);
      } catch (_) {}
    };

    ws.onerror = () => {
      if (mountedRef.current) setWsStatus("error");
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setWsStatus("disconnected");
      reconnectRef.current = setTimeout(connectWs, RECONNECT_DELAY_MS);
    };
  }, [sessionId]);

  useEffect(() => {
    mountedRef.current = true;
    connectWs();
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      clearTimeout(reconnectRef.current);
    };
  }, [connectWs]);

  // ── Smart Cropping & Payload Generation ──────────────────────────────────
  const handleFacesDetected = useCallback((faces, video) => {
    if (sendingRef.current) return;
    
    // Rate limit to roughly CAPTURE_INTERVAL_MS
    const now = Date.now();
    if (now - lastSendTimeRef.current < CAPTURE_INTERVAL_MS) return;
    
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return;

    const ctx = canvas.getContext("2d", { willReadFrequently: false });
    if (!ctx) return;

    sendingRef.current = true;
    try {
      const sw = video.videoWidth || 640;
      const sh = video.videoHeight || 360;
      
      const payloadFaces = [];
      
      if (!faces || faces.length === 0) {
        // Send an empty frame payload so the backend knows faces disappeared (to clear trackers)
        const payload = JSON.stringify({ faces: [], frame_size: { width: sw, height: sh } });
        ws.send(payload);
        lastSendTimeRef.current = now;
        sendingRef.current = false;
        return;
      }
      
      // Crop each face
      for (const face of faces) {
         if (!face.rawBox) continue;
         
         const rawBox = face.rawBox;
         // Add 30% padding around the face for ArcFace alignment to work perfectly
         const padX = rawBox.w * 0.3;
         const padY = rawBox.h * 0.3;
         
         const cx = Math.max(0, rawBox.x - padX);
         const cy = Math.max(0, rawBox.y - padY);
         const cw = Math.min(sw - cx, rawBox.w + padX * 2);
         const ch = Math.min(sh - cy, rawBox.h + padY * 2);
         
         // Downscale to max 150x150 to keep payload microscopic
         const maxCropSize = 150;
         const scale = Math.min(1, maxCropSize / cw, maxCropSize / ch);
         const dw = Math.max(1, Math.round(cw * scale));
         const dh = Math.max(1, Math.round(ch * scale));
         
         canvas.width = dw;
         canvas.height = dh;
         // Draw just the face region onto the canvas
         ctx.drawImage(video, cx, cy, cw, ch, 0, 0, dw, dh);
         
         const base64Data = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
         const base64Image = base64Data.split(",")[1];
         
         // Convert normalized keypoints to crop-relative pixels and build lm5
         let lm5 = [];
         if (face.keypoints && face.keypoints.length >= 4) {
             const kp = face.keypoints;
             const toCropX = (nx) => (nx * sw - cx) * (dw / cw);
             const toCropY = (ny) => (ny * sh - cy) * (dh / ch);
             
             let ex1 = toCropX(kp[0].x), ey1 = toCropY(kp[0].y);
             let ex2 = toCropX(kp[1].x), ey2 = toCropY(kp[1].y);
             
             let left_eye = ex1 < ex2 ? {x: ex1, y: ey1} : {x: ex2, y: ey2};
             let right_eye = ex1 < ex2 ? {x: ex2, y: ey2} : {x: ex1, y: ey1};
             let nose = {x: toCropX(kp[2].x), y: toCropY(kp[2].y)};
             let mouth_c = {x: toCropX(kp[3].x), y: toCropY(kp[3].y)};
             
             let eye_dx = right_eye.x - left_eye.x;
             let left_mouth = {x: mouth_c.x - eye_dx * 0.4, y: mouth_c.y};
             let right_mouth = {x: mouth_c.x + eye_dx * 0.4, y: mouth_c.y};
             
             lm5 = [
                 [left_eye.x, left_eye.y],
                 [right_eye.x, right_eye.y],
                 [nose.x, nose.y],
                 [left_mouth.x, left_mouth.y],
                 [right_mouth.x, right_mouth.y]
             ];
         }
         
         payloadFaces.push({
            bbox: [rawBox.x, rawBox.y, rawBox.x + rawBox.w, rawBox.y + rawBox.h],
            landmark: lm5,
            image_base64: base64Image
         });
      }
      
      const payload = JSON.stringify({ faces: payloadFaces, frame_size: { width: sw, height: sh } });
      ws.send(payload);
      
      lastSendTimeRef.current = now;
      sendingRef.current = false;
    } catch (_) {
      sendingRef.current = false;
    }
  }, []);

  // ── Camera device management ──────────────────────────────────────────────
  const stopStream = useCallback(() => {
    if (timerRef.current) {
       clearInterval(timerRef.current);
       timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const startCamera = useCallback(
    async (deviceId = "") => {
      stopStream();
      setCameraError("");

      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("This browser does not support camera access.");
        }

        const constraints = {
          video: deviceId
            ? { deviceId: { exact: deviceId } }
            : { facingMode: "user" },
          audio: false,
        };

        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        if (!mountedRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          try {
            await videoRef.current.play();
          } catch (err) {
            // Browser may interrupt play() if this tile immediately switches
            // from the default camera to a concrete deviceId.
            if (err?.name !== "AbortError") {
              throw err;
            }
          }
        }

        // Enumerate all camera devices after permission is granted
        const allDevices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = allDevices.filter((d) => d.kind === "videoinput");
        if (mountedRef.current) {
          setDevices(videoDevices);
          if (!deviceId && videoDevices.length > 0) {
            skipNextDeviceStartRef.current = true;
            setSelectedDeviceId(videoDevices[0].deviceId);
          }
        }
      } catch (err) {
        if (mountedRef.current) {
          setCameraError(
            err instanceof Error ? err.message : "Unable to access camera",
          );
        }
      }
    },
    [stopStream],
  );

  // Initial camera start on mount
  useEffect(() => {
    startCamera();
    return () => stopStream();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Camera switch when user picks a different device
  useEffect(() => {
    if (!selectedDeviceId) return;
    if (skipNextDeviceStartRef.current) {
      skipNextDeviceStartRef.current = false;
      return;
    }
    startCamera(selectedDeviceId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDeviceId]);

  return {
    videoRef,
    canvasRef,
    devices,
    selectedDeviceId,
    setSelectedDeviceId,
    wsStatus,
    customers,
    frameSize,
    cameraError,
    handleFacesDetected,
  };
}
