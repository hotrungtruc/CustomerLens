"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const CAPTURE_INTERVAL_MS = 50; // 20 fps
const JPEG_QUALITY = 0.75;
const MAX_UPLOAD_WIDTH = 640;
const MAX_UPLOAD_HEIGHT = 360;
const RECONNECT_DELAY_MS = 2000;

function getWsUrl(cameraId, takeover = false) {
  // Derive WS URL from the API base URL so it works in any environment
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  let host = `${window.location.hostname}:8000`;
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
  const query = takeover ? "?takeover=1" : "";
  return `${protocol}//${host}/ws/${encodeURIComponent(cameraId)}${query}`;
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
export function useCamera(cameraId) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const wsRef = useRef(null);
  const mountedRef = useRef(true);
  const sendingRef = useRef(false);
  const reconnectRef = useRef(null);
  const takeoverNextRef = useRef(false);
  const suppressedCloseRef = useRef(null);
  const serverReadyRef = useRef(false);
  const skipNextDeviceStartRef = useRef(false);
  const peerConnectionsRef = useRef({});

  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [wsStatus, setWsStatus] = useState("connecting");
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [cameraError, setCameraError] = useState("");
  const [connectionId, setConnectionId] = useState(null);

  // ── WebSocket lifecycle ───────────────────────────────────────────────────
  const connectWs = useCallback(() => {
    if (!mountedRef.current) return;

    const takeover = takeoverNextRef.current;
    takeoverNextRef.current = false;
    const ws = new WebSocket(getWsUrl(cameraId, takeover));
    wsRef.current = ws;
    serverReadyRef.current = false;
    setConnectionId(null);
    setWsStatus("connecting");

    ws.onmessage = async (event) => {
      if (!mountedRef.current || wsRef.current !== ws) return;
      try {
        const data = JSON.parse(event.data);

        if (data.type === "ready") {
          serverReadyRef.current = true;
          setConnectionId(data.connection_id);
          setWsStatus("live");
          return;
        }
        
        // Handle AI Tracking Data
        if (data.customers) {
          if (data.frame_size?.width) setFrameSize(data.frame_size);
          setCustomers(data.customers);
          return;
        }
        
        // Handle WebRTC Signaling
        if (data.type === "webrtc_offer") {
          const adminId = data.admin_id;
          const pc = new RTCPeerConnection({
            iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
          });
          peerConnectionsRef.current[adminId] = pc;
          
          if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => {
              pc.addTrack(track, streamRef.current);
            });
          }
          
          pc.onicecandidate = (e) => {
            if (e.candidate && wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({
                type: "webrtc_ice",
                admin_id: adminId,
                candidate: e.candidate
              }));
            }
          };
          
          await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          
          wsRef.current.send(JSON.stringify({
            type: "webrtc_answer",
            admin_id: adminId,
            sdp: answer
          }));
        } else if (data.type === "webrtc_ice" && data.admin_id) {
          const pc = peerConnectionsRef.current[data.admin_id];
          if (pc && data.candidate) {
            await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
          }
        }
      } catch (e) {
        console.error("WS Message Error", e);
      }
    };

    ws.onerror = () => {
      if (mountedRef.current && wsRef.current === ws) setWsStatus("error");
    };

    ws.onclose = (event) => {
      if (!mountedRef.current || wsRef.current !== ws) return;
      if (suppressedCloseRef.current === ws) {
        suppressedCloseRef.current = null;
        return;
      }
      wsRef.current = null;
      serverReadyRef.current = false;
      setConnectionId(null);
      if (event.code === 4008) {
        setWsStatus("taken_over");
        return;
      }
      setWsStatus("disconnected");
      reconnectRef.current = setTimeout(connectWs, RECONNECT_DELAY_MS);
    };
  }, [cameraId]);

  useEffect(() => {
    mountedRef.current = true;
    connectWs();
    return () => {
      mountedRef.current = false;
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
      clearTimeout(reconnectRef.current);
    };
  }, [connectWs]);

  const takeOver = useCallback(() => {
    clearTimeout(reconnectRef.current);
    takeoverNextRef.current = true;
    const currentWs = wsRef.current;
    if (currentWs && currentWs.readyState < WebSocket.CLOSING) {
      suppressedCloseRef.current = currentWs;
      currentWs.close();
    }
    setTimeout(connectWs, 0);
  }, [connectWs]);

  // ── Frame capture ─────────────────────────────────────────────────────────
  const sendFrame = useCallback(() => {
    if (!serverReadyRef.current) return;
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
          if (
            serverReadyRef.current &&
            wsRef.current === ws &&
            ws.readyState === WebSocket.OPEN &&
            blob
          ) {
            ws.send(blob);
          }
          sendingRef.current = false;
        },
        "image/jpeg",
        JPEG_QUALITY,
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
    
    // Close all WebRTC connections
    Object.values(peerConnectionsRef.current).forEach(pc => pc.close());
    peerConnectionsRef.current = {};
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
            ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, frameRate: { ideal: 60 } }
            : { facingMode: "user", width: { ideal: 1280 }, frameRate: { ideal: 60 } },
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
          setCameraError(
            err instanceof Error ? err.message : "Unable to access camera",
          );
        }
      }
    },
    [stopStream, sendFrame],
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
    connectionId,
    takeOver,
    customers,
    frameSize,
    cameraError,
  };
}
