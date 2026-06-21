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
 * useCameraObserver — read-only WebSocket that receives annotations
 * from a remote camera session without sending any frames.
 */
export function useCameraObserver(sessionId) {
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [status, setStatus] = useState("connecting");
  const wsRef = useRef(null);
  const mountedRef = useRef(true);
  const reconnectRef = useRef(null);

  const connect = useCallback(() => {
    if (!mountedRef.current || !sessionId) return;

    const ws = new WebSocket(getObserveWsUrl(sessionId));
    wsRef.current = ws;
    setStatus("connecting");

    ws.onopen = () => {
      if (mountedRef.current) setStatus("live");
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
      if (mountedRef.current) setStatus("error");
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus("disconnected");
      reconnectRef.current = setTimeout(connect, 3000);
    };
  }, [sessionId]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      clearTimeout(reconnectRef.current);
    };
  }, [connect]);

  return { customers, frameSize, status };
}
