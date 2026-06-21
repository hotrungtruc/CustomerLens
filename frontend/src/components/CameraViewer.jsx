"use client";

import { useEffect, useRef, useState } from "react";
import { useCameraObserver } from "../hooks/useCameraObserver";
import { getTrackBadge, TRACK_BADGE_THEMES } from "../lib/trackBadge";
import { API_BASE_URL } from "../services/api";

/**
 * CameraViewer — read-only viewer for a remote camera session.
 *
 * Polls the backend snapshot endpoint for JPEG frames and uses
 * the observe WebSocket for annotation overlays. Does NOT open
 * the local webcam.
 */
export default function CameraViewer({ sessionId, compact = false }) {
  const imgRef = useRef(null);
  const { customers, frameSize, status } = useCameraObserver(sessionId);
  const [imageSrc, setImageSrc] = useState(null);

  // Poll for snapshot frames (~5 fps)
  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    const url = `${API_BASE_URL}/api/camera_snapshot/${encodeURIComponent(sessionId)}`;

    async function fetchFrame() {
      try {
        const res = await fetch(url);
        if (res.ok && active) {
          const blob = await res.blob();
          const objectUrl = URL.createObjectURL(blob);
          setImageSrc((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return objectUrl;
          });
        }
      } catch (_) {}
      if (active) timer = setTimeout(fetchFrame, 200);
    }

    let timer = setTimeout(fetchFrame, 0);
    return () => {
      active = false;
      clearTimeout(timer);
      setImageSrc((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [sessionId]);

  // Build bounding boxes from observer annotations
  const boxes = customers
    .filter((c) => Array.isArray(c.bbox) && c.bbox.length === 4)
    .map((c) => {
      const [x1, y1, x2, y2] = c.bbox;
      const badge = getTrackBadge(c.track_id);
      const theme = badge.theme;
      return {
        ...c,
        left: (x1 / frameSize.width) * 100,
        top: (y1 / frameSize.height) * 100,
        width: ((x2 - x1) / frameSize.width) * 100,
        height: ((y2 - y1) / frameSize.height) * 100,
        symbol: badge.symbol,
        bgClass: theme.base,
      };
    });

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-950">
      {/* Video frame */}
      {imageSrc ? (
        <img
          ref={imgRef}
          src={imageSrc}
          alt={`Camera ${sessionId}`}
          className="h-full w-full object-cover"
          draggable={false}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <div className="flex flex-col items-center gap-2">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white/80" />
            <span className="text-[11px] text-white/50">Đang kết nối…</span>
          </div>
        </div>
      )}

      {/* Bounding box overlays (only in expanded / non-compact mode) */}
      {!compact &&
        boxes.map((box) => (
          <div
            key={box.track_id}
            className="absolute rounded-md border-2 border-white/70 pointer-events-none transition-all duration-150"
            style={{
              left: `${box.left}%`,
              top: `${box.top}%`,
              width: `${box.width}%`,
              height: `${box.height}%`,
            }}
          >
            {/* Badge */}
            <div
              className={`absolute -top-3 left-1/2 -translate-x-1/2 flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold text-white shadow ${box.bgClass}`}
            >
              {box.symbol}
            </div>
          </div>
        ))}

      {/* Face count badge (compact mode) */}
      {compact && boxes.length > 0 && (
        <div className="absolute bottom-2 left-2 flex items-center gap-1">
          {boxes.slice(0, 3).map((box) => (
            <div
              key={box.track_id}
              className={`flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold text-white shadow-lg ring-2 ring-white/40 ${box.bgClass}`}
            >
              {box.symbol}
            </div>
          ))}
          {boxes.length > 3 && (
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-700 text-[10px] font-bold text-white shadow-lg ring-2 ring-white/40">
              +{boxes.length - 3}
            </div>
          )}
        </div>
      )}

      {/* Connection status overlay */}
      {status !== "live" && imageSrc && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950/50 backdrop-blur-sm">
          <span className="text-xs font-medium text-white/80">
            {status === "connecting" ? "Đang kết nối…" : "Mất kết nối"}
          </span>
        </div>
      )}
    </div>
  );
}
