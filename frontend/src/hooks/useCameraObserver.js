"use client";

import { useCallback, useEffect, useRef, useState } from "react";

function getObserveWsUrl(sessionId) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  let host = "localhost:8000";
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
  return `${protocol}//${host}/ws/observe/${encodeURIComponent(sessionId)}`;
}

/**
 * useCameraObserver — read-only WebSocket + WebRTC that receives annotations
 * and WebRTC video stream from a remote camera session.
 */
export function useCameraObserver(sessionId) {
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
    if (!mountedRef.current || !sessionId) return;

    const ws = new WebSocket(getObserveWsUrl(sessionId));
    wsRef.current = ws;
    setStatus("connecting");

    ws.onopen = async () => {
      if (!mountedRef.current) return;
      setStatus("live");
      
      // Initialize WebRTC on WS open
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
      
      // Create Offer
      try {
        // Add a transceiver to force receiving video
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

    ws.onmessage = async (event) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(event.data);
        
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
      if (mountedRef.current) setStatus("error");
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus("disconnected");
      setVideoStream(null);
      pcRef.current?.close();
      pcRef.current = null;
      reconnectRef.current = setTimeout(connect, 3000);
    };
  }, [sessionId]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      pcRef.current?.close();
      clearTimeout(reconnectRef.current);
    };
  }, [connect]);

  return { customers, frameSize, status, videoStream };
}
