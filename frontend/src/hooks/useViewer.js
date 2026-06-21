"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const RECONNECT_DELAY_MS = 2000;

function getSubscribeWsUrl(sessionId) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  let host = "localhost:8000";
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_HOST;
  if (baseUrl) {
    try {
      const url = baseUrl.includes("://") ? new URL(baseUrl) : new URL(`http://${baseUrl}`);
      host = url.host;
    } catch (_) {
      host = baseUrl.replace(/^https?:\/\//, "");
    }
  }
  return `${protocol}//${host}/ws/subscribe/${encodeURIComponent(sessionId)}`;
}

export function useViewer(sessionId) {
  const wsRef = useRef(null);
  const mountedRef = useRef(true);
  const reconnectRef = useRef(null);

  const [wsStatus, setWsStatus] = useState("connecting");
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [imageUrl, setImageUrl] = useState(null);

  const connectWs = useCallback(() => {
    if (!mountedRef.current) return;

    const ws = new WebSocket(getSubscribeWsUrl(sessionId));
    wsRef.current = ws;
    setWsStatus("connecting");

    ws.onopen = () => {
      if (mountedRef.current) setWsStatus("live");
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      
      // If binary (Blob), it's the JPEG frame
      if (event.data instanceof Blob) {
        const url = URL.createObjectURL(event.data);
        setImageUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev); // clean up old url to avoid memory leak
          return url;
        });
        return;
      }

      // If text, it's the JSON annotations
      if (typeof event.data === "string") {
        try {
          const data = JSON.parse(event.data);
          if (data.frame_size?.width) setFrameSize(data.frame_size);
          setCustomers(data.customers ?? []);
        } catch (_) {}
      }
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

  return {
    wsStatus,
    customers,
    frameSize,
    imageUrl,
  };
}
