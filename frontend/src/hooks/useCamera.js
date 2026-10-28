"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const CAPTURE_INTERVAL_MS = 50; // 20 fps
const JPEG_QUALITY = 0.75;
const MAX_UPLOAD_WIDTH = 640;
const MAX_UPLOAD_HEIGHT = 360;
const RECONNECT_DELAY_MS = 2000;

function getWsUrl(cameraId, takeover = false) {
  const protocol = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:";
  let baseUrl =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_HOST ||
    "";
  if (!baseUrl || (baseUrl.includes("checkinface.me") && !baseUrl.includes("api.checkinface.me"))) {
    baseUrl = "https://api.checkinface.me";
  }
  let host;
  try {
    const url = baseUrl.includes("://") ? new URL(baseUrl) : new URL(`http://${baseUrl}`);
    host = url.host;
  } catch (_) {
    host = baseUrl.replace(/^https?:\/\//, "").replace(/\/.*$/, "");
  }
  if (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") && !process.env.NEXT_PUBLIC_API_URL && !process.env.NEXT_PUBLIC_API_BASE_URL) {
    host = "localhost:8000";
  }
  const query = "?takeover=1";
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
  const takeoverNextRef = useRef(true);
  const suppressedCloseRef = useRef(null);
  const serverReadyRef = useRef(false);
  const skipNextDeviceStartRef = useRef(false);
  const peerConnectionsRef = useRef({});
  const faceImagesRef = useRef({});

  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("sample_video");
  const [wsStatus, setWsStatus] = useState("connecting");
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [cameraError, setCameraError] = useState("");
  const [connectionId, setConnectionId] = useState(null);
  const [edgeSettings, setEdgeSettings] = useState({
    edge_crop_padding: 0.8,
    edge_send_interval_ms: 200
  });

  // Load edge tracking settings
  useEffect(() => {
    if (typeof window === "undefined") return;
    import("../services/api").then(({ fetchSettings }) => {
      fetchSettings().then(data => {
        setEdgeSettings(prev => ({
          edge_crop_padding: data.edge_crop_padding ?? prev.edge_crop_padding,
          edge_send_interval_ms: data.edge_send_interval_ms ?? prev.edge_send_interval_ms
        }));
      }).catch(console.error);
    }).catch(console.error);
  }, []);

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
        if (data.type === "camera_update" || data.customers) {
          console.log("[WS] Received camera_update:", JSON.stringify(data).slice(0, 200));
          if (data.frame_size?.width) setFrameSize(data.frame_size);
          setCustomers(prev => {
            let next = [...prev];
            data.customers.forEach(c => {
               const key = c.local_track_id || c.track_id;
               const idx = next.findIndex(x => (x.local_track_id || x.track_id) === key);
               if (idx >= 0) next[idx] = { ...c, last_seen: Date.now() };
               else next.push({ ...c, last_seen: Date.now() });
            });
            const now = Date.now();
            return next.filter(x => {
              const isResolved = Boolean(x.id && x.customer_status !== "extracting" && x.name !== "Đang nhận diện..." && x.name !== "Identifying...");
              const maxAge = isResolved ? 10000 : 2500;
              return now - (x.last_seen || now) < maxAge;
            });
          });
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
        clearTimeout(reconnectRef.current);
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
    setWsStatus("connecting");
    const currentWs = wsRef.current;
    if (currentWs && currentWs.readyState < WebSocket.CLOSING) {
      suppressedCloseRef.current = currentWs;
      currentWs.close();
    }
    setTimeout(connectWs, 0);
  }, [connectWs]);

  // ── Frame capture ─────────────────────────────────────────────────────────
  const sendCrop = useCallback((face) => {
    if (!face || !face.pixelBox) return;
    const { originX, originY, width, height } = face.pixelBox;
    if (width < 32 || height < 32) return;
    if (face.isGoodQuality === false) return;
    if (face.score && face.score < 0.55) return;

    if (!serverReadyRef.current) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const video = videoRef.current;
    if (!video || video.readyState < 2) return;

    // Create a dynamic canvas to avoid race conditions when sending multiple crops asynchronously
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: false });
    if (!ctx) return;

    try {
      
      // Use 50% padding (+50%) to include chin/forehead/ears and provide ideal context for backend SCRFD & ArcFace
      const paddingRatio = 0.50;
      const padX = width * paddingRatio;
      const padY = height * paddingRatio;
      
      const sx = Math.max(0, originX - padX);
      const sy = Math.max(0, originY - padY);
      const sWidth = Math.min(video.videoWidth - sx, width + padX * 2);
      const sHeight = Math.min(video.videoHeight - sy, height + padY * 2);
      
      // Limit resolution to 320x320 for cropped faces to save bandwidth
      const scale = Math.min(1, 320 / sWidth, 320 / sHeight);
      const w = Math.max(1, Math.round(sWidth * scale));
      const h = Math.max(1, Math.round(sHeight * scale));
      
      canvas.width = w;
      canvas.height = h;
      ctx.drawImage(video, sx, sy, sWidth, sHeight, 0, 0, w, h);

      // Save immediate face crop thumbnail for UI overlay & pinned inspector
      if (!faceImagesRef.current[face.local_track_id]) {
        faceImagesRef.current[face.local_track_id] = canvas.toDataURL("image/jpeg", 0.85);
      }

      // Blur Detection (Laplacian Variance)
      const imageData = ctx.getImageData(0, 0, w, h);
      const data = imageData.data;
      let sum = 0, sumSq = 0;
      let validPixels = 0;
      // Simple laplacian kernel approximation for speed: [0, 1, 0, 1, -4, 1, 0, 1, 0]
      // We sample every 4th pixel for speed
      for (let y = 1; y < h - 1; y += 2) {
        for (let x = 1; x < w - 1; x += 2) {
          const i = (y * w + x) * 4;
          // Grayscale values
          const c = (data[i] + data[i+1] + data[i+2]) / 3;
          const t = (data[i - w*4] + data[i+1 - w*4] + data[i+2 - w*4]) / 3;
          const b = (data[i + w*4] + data[i+1 + w*4] + data[i+2 + w*4]) / 3;
          const l = (data[i - 4] + data[i+1 - 4] + data[i+2 - 4]) / 3;
          const r = (data[i + 4] + data[i+1 + 4] + data[i+2 + 4]) / 3;
          
          const laplacian = t + b + l + r - 4 * c;
          sum += laplacian;
          sumSq += laplacian * laplacian;
          validPixels++;
        }
      }
      const mean = sum / validPixels;
      const variance = (sumSq / validPixels) - (mean * mean);
      
      const minVariance = 0.5;
      if (variance < minVariance) {
        // Blur detected, ignore frame for embedding
        return;
      }

      // Update with sharper crop if available
      if (variance > 10) {
        faceImagesRef.current[face.local_track_id] = canvas.toDataURL("image/jpeg", 0.85);
      }

      canvas.toBlob(
        (blob) => {
          if (
            serverReadyRef.current &&
            wsRef.current === ws &&
            ws.readyState === WebSocket.OPEN &&
            blob
          ) {
            blob.arrayBuffer().then(blobBuffer => {
               const transformed_landmarks = [];
               if (face.keypoints && face.keypoints.length >= 4) {
                   for (const pt of face.keypoints) {
                       if (pt) {
                           const px = pt.px !== undefined ? pt.px : pt.x * video.videoWidth;
                           const py = pt.py !== undefined ? pt.py : pt.y * video.videoHeight;
                           const cropX = (px - sx) * scale;
                           const cropY = (py - sy) * scale;
                           transformed_landmarks.push([cropX, cropY]);
                       }
                   }
               }
               
               const metaJson = JSON.stringify({
                   local_track_id: face.local_track_id,
                   bbox: [sx, sy, sx + sWidth, sy + sHeight],
                   landmarks: (transformed_landmarks.length === 4 || transformed_landmarks.length === 5) ? transformed_landmarks : null
               });
               const metaBytes = new TextEncoder().encode(metaJson);
               
               // Use DataView to ensure Big-Endian encoding for the length (matching Python's int.from_bytes(..., byteorder="big"))
               const metaLenBuf = new ArrayBuffer(4);
               new DataView(metaLenBuf).setUint32(0, metaBytes.length, false); 
               
               const combined = new Uint8Array(4 + metaBytes.length + blobBuffer.byteLength);
               combined.set(new Uint8Array(metaLenBuf), 0);
               combined.set(metaBytes, 4);
               combined.set(new Uint8Array(blobBuffer), 4 + metaBytes.length);
               
               if (ws.readyState === WebSocket.OPEN) {
                  ws.send(combined);
                  console.log(`[sendCrop] Sent edge crop for track=${face.local_track_id}, size=${combined.byteLength}b`);
                }
            }).catch(err => console.error("Blob array buffer error", err));
          }
        },
        "image/jpeg",
        JPEG_QUALITY,
      );
    } catch (_) {
    }
  }, [edgeSettings]);

  // ── Camera device management ──────────────────────────────────────────────
  const stopStream = useCallback(() => {
    clearInterval(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    
    if (videoRef.current) {
      try {
        videoRef.current.pause();
        videoRef.current.removeAttribute("src");
        videoRef.current.src = "";
        videoRef.current.load();
      } catch (_) {}
      videoRef.current.srcObject = null;
    }

    // Close all WebRTC connections
    Object.values(peerConnectionsRef.current).forEach(pc => pc.close());
    peerConnectionsRef.current = {};
  }, []);

  const startCamera = useCallback(
    async (deviceId = "") => {
      stopStream();
      setCameraError("");

      // Direct video stream simulation (sample video or uploaded blob)
      if (deviceId === "sample_video" || deviceId.startsWith("blob:") || deviceId.endsWith(".mp4")) {
        if (videoRef.current) {
          const videoSrc = deviceId === "sample_video" ? "/test_video.mp4" : deviceId;
          videoRef.current.srcObject = null;
          videoRef.current.src = videoSrc;
          videoRef.current.loop = true;
          videoRef.current.muted = true;
          videoRef.current.playsInline = true;
          try {
            await videoRef.current.play();
          } catch (err) {
            console.warn("Video file play error:", err);
          }
        }
        return;
      }

      // Live Physical Webcam Stream
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("Trình duyệt không hỗ trợ MediaDevices / Webcam API.");
        }

        let stream = null;
        try {
          const constraints = {
            video: deviceId
              ? { deviceId: { exact: deviceId } }
              : { width: { ideal: 1280 }, height: { ideal: 720 } },
            audio: false,
          };
          stream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (firstErr) {
          console.warn("Camera constraint failed, retrying with default { video: true }", firstErr);
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        }

        if (!mountedRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.pause();
          videoRef.current.removeAttribute("src");
          videoRef.current.src = "";
          videoRef.current.loop = false;
          videoRef.current.srcObject = stream;
          try {
            await videoRef.current.play();
          } catch (err) {
            if (err?.name !== "AbortError") {
              throw err;
            }
          }
        }

        // Enumerate all camera devices after permission is granted
        try {
          const allDevices = await navigator.mediaDevices.enumerateDevices();
          const videoDevices = allDevices.filter((d) => d.kind === "videoinput");
          if (mountedRef.current) {
            setDevices(videoDevices);
          }
        } catch (_) {}
      } catch (err) {
        console.error("Camera access error:", err);
        if (mountedRef.current) {
          let errorMsg = err instanceof Error ? err.message : "Unable to access camera";
          if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
            errorMsg = "Quyền truy cập camera bị từ chối. Vui lòng cho phép quyền Camera trên trình duyệt.";
          } else if (err?.name === "NotFoundError" || err?.name === "DevicesNotFoundError") {
            errorMsg = "Không tìm thấy thiết bị camera nào được kết nối với máy tính.";
          } else if (err?.name === "NotReadableError" || err?.name === "TrackStartError") {
            errorMsg = "Không thể khởi động camera. Có thể camera đang được ứng dụng khác (Zoom, Teams, v.v.) chiếm giữ.";
          }
          setCameraError(errorMsg);
        }
      }
    },
    [stopStream],
  );

  // Initial enumeration on mount
  useEffect(() => {
    if (typeof navigator !== "undefined" && navigator.mediaDevices?.enumerateDevices) {
      navigator.mediaDevices.enumerateDevices().then((allDevices) => {
        const videoDevices = allDevices.filter((d) => d.kind === "videoinput");
        if (mountedRef.current && videoDevices.length > 0) {
          setDevices(videoDevices);
        }
      }).catch(() => {});
    }
  }, []);

  const isFirstMountRef = useRef(true);

  // Camera switch whenever selectedDeviceId changes (including empty string for Integrated Camera)
  useEffect(() => {
    if (isFirstMountRef.current) {
      isFirstMountRef.current = false;
      startCamera(selectedDeviceId);
      return;
    }
    startCamera(selectedDeviceId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDeviceId]);

  // Stop stream tracks on unmount
  useEffect(() => {
    return () => stopStream();
  }, [stopStream]);

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
    sendCrop,
    edgeSettings,
    faceImagesRef,
  };
}
