"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const OBSERVER_WS_SUBPROTOCOL = "camera-observer";

function getObserveWsUrl(cameraId) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  let host = `${window.location.hostname}:8000`;
  const baseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_HOST;
  if (baseUrl) {
    try {
      const url = baseUrl.includes("://")
        ? new URL(baseUrl)
        : new URL(`http://${baseUrl}`);
      host = url.host;
    } catch (_) {
      host = baseUrl.replace(/^https?:\/\//, "");
    }
  }
  return `${protocol}//${host}/ws/observe/${encodeURIComponent(cameraId)}`;
}

/**
 * useCameraObserver — read-only WebSocket + WebRTC that receives annotations
 * and WebRTC video stream from a remote camera session.
 */
export function useCameraObserver(cameraId) {
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [status, setStatus] = useState("connecting");
  const [videoStream, setVideoStream] = useState(null);
  
  const wsRef = useRef(null);
  const pcRef = useRef(null);
  const mountedRef = useRef(true);
  const reconnectRef = useRef(null);
  const adminIdRef = useRef(crypto.randomUUID());

  const connect = useCallback(() => {
    if (!mountedRef.current || !cameraId) return;

    const token = localStorage.getItem("token");
    if (!token) {
      setStatus("error");
      return;
    }

    const ws = new WebSocket(getObserveWsUrl(cameraId), [
      OBSERVER_WS_SUBPROTOCOL,
      token,
    ]);
    wsRef.current = ws;
    setStatus("connecting");

    const startPeerConnection = async () => {
      if (!mountedRef.current) return;
      pcRef.current?.close();
      setVideoStream(null);
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
      });
      pcRef.current = pc;
      
      pc.ontrack = (event) => {
        if (event.streams && event.streams[0]) {
          setVideoStream(event.streams[0]);
        }
      };
      
      pc.onicecandidate = (e) => {
        if (e.candidate && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: "webrtc_ice",
            admin_id: adminIdRef.current,
            candidate: e.candidate
          }));
        }
      };
      
      try {
        pc.addTransceiver('video', { direction: 'recvonly' });
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        ws.send(JSON.stringify({
          type: "webrtc_offer",
          admin_id: adminIdRef.current,
          sdp: offer
        }));
      } catch (err) {
        console.error("Error creating WebRTC offer", err);
      }
    };

    ws.onopen = async () => {
      if (!mountedRef.current) return;
      setStatus("live");
      await startPeerConnection();
    };

    ws.onmessage = async (event) => {
      if (!mountedRef.current || wsRef.current !== ws) return;
      try {
        const data = JSON.parse(event.data);

        if (data.type === "publisher_ready") {
          await startPeerConnection();
          return;
        }

        if (data.type === "publisher_offline") {
          pcRef.current?.close();
          pcRef.current = null;
          setVideoStream(null);
          return;
        }
        
        // Handle AI Tracking Data
        if (data.customers) {
          if (data.frame_size?.width) setFrameSize(data.frame_size);
          setCustomers(data.customers);
          return;
        }
        
        // Handle WebRTC Signaling from Camera
        if (data.type === "webrtc_answer" && data.admin_id === adminIdRef.current) {
          const pc = pcRef.current;
          if (pc && pc.signalingState !== "stable") {
            await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
          }
        } else if (data.type === "webrtc_ice" && data.admin_id === adminIdRef.current) {
          const pc = pcRef.current;
          if (pc && data.candidate) {
            await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
          }
        }
      } catch (_) {}
    };

    ws.onerror = () => {
      if (mountedRef.current && wsRef.current === ws) setStatus("error");
    };

    ws.onclose = () => {
      if (!mountedRef.current || wsRef.current !== ws) return;
      wsRef.current = null;
      setStatus("disconnected");
      setVideoStream(null);
      pcRef.current?.close();
      pcRef.current = null;
      reconnectRef.current = setTimeout(connect, 3000);
    };
  }, [cameraId]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
      pcRef.current?.close();
      clearTimeout(reconnectRef.current);
    };
  }, [connect]);

  return { customers, frameSize, status, videoStream };
}
