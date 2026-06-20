"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const CAPTURE_INTERVAL_MS = 50;   // 20 fps
const JPEG_QUALITY = 0.75;
const MAX_UPLOAD_WIDTH = 640;
const MAX_UPLOAD_HEIGHT = 360;
const RECONNECT_DELAY_MS = 2000;

function getWsUrl(sessionId) {
  // Derive WS URL from current page origin so it works in any environment
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = process.env.NEXT_PUBLIC_API_HOST || "localhost:8000";
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

  // ── Frame capture ─────────────────────────────────────────────────────────
  const sendFrame = useCallback(() => {
    if (sendingRef.current) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return;

    const ctx = canvas.getContext("2d", { willReadFrequently: false });
    if (!ctx) return;

    sendingRef.current = true;
    try {
      const sw = video.videoWidth || 640;
      const sh = video.videoHeight || 360;
      const scale = Math.min(1, MAX_UPLOAD_WIDTH / sw, MAX_UPLOAD_HEIGHT / sh);
      const w = Math.max(1, Math.round(sw * scale));
      const h = Math.max(1, Math.round(sh * scale));
      canvas.width = w;
      canvas.height = h;
      ctx.drawImage(video, 0, 0, w, h);
      
      canvas.toBlob(
        (blob) => {
          if (wsRef.current?.readyState === WebSocket.OPEN && blob) {
            wsRef.current.send(blob);
          }
          sendingRef.current = false;
        },
        "image/jpeg",
        JPEG_QUALITY
      );
    } catch (_) {
      sendingRef.current = false;
    }
  }, []);

  // ── Camera device management ──────────────────────────────────────────────
  const stopStream = useCallback(() => {
    clearInterval(timerRef.current);
    timerRef.current = null;
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
          video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "user" },
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

        timerRef.current = setInterval(sendFrame, CAPTURE_INTERVAL_MS);
      } catch (err) {
        if (mountedRef.current) {
          setCameraError(err instanceof Error ? err.message : "Unable to access camera");
        }
      }
    },
    [stopStream, sendFrame]
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
  };
}
