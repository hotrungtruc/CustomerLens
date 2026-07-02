"use client";

import { useEffect, useRef, useState } from "react";
import { useCameraObserver } from "../hooks/useCameraObserver";
import { useVideoBbox } from "../hooks/useVideoBbox";
import { getTrackBadge, TRACK_BADGE_THEMES } from "../lib/trackBadge";

/**
 * CameraViewer — read-only viewer for a remote camera session.
 *
 * Polls the backend snapshot endpoint for JPEG frames and uses
 * the observe WebSocket for annotation overlays. Does NOT open
 * the local webcam.
 */
export default function CameraViewer({ cameraId, compact = false }) {
  const { customers, frameSize, status, videoStream } = useCameraObserver(cameraId);
  const videoRef = useRef(null);

  // Poll for snapshot frames - REMOVED! We now use WebRTC videoStream.

  // Attach WebRTC stream to video element
  useEffect(() => {
    if (videoRef.current && videoStream) {
      videoRef.current.srcObject = videoStream;
    }
  }, [videoStream]);

  const mapBbox = useVideoBbox(videoRef, frameSize.width, frameSize.height);

  // Build bounding boxes from observer annotations
  const boxes = customers
    .filter((c) => Array.isArray(c.bbox) && c.bbox.length === 4)
    .map((c) => {
      const [x1, y1, x2, y2] = c.bbox;
      const badge = getTrackBadge(c.track_id);
      const theme = badge.theme;
      const mapped = mapBbox(x1, y1, x2 - x1, y2 - y1);
      return {
        ...c,
        left: mapped.left,
        top: mapped.top,
        width: mapped.width,
        height: mapped.height,
        symbol: badge.symbol,
        bgClass: theme.base,
      };
    });

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-950">
      {/* Video frame */}
      {videoStream ? (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="h-full w-full object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <div className="flex flex-col items-center gap-2">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white/80" />
            <span className="text-[11px] text-white/50">Đang kết nối…</span>
          </div>
        </div>
      )}

      {/* Bounding box overlays */}
      {boxes.map((box) => (
        <div
          key={box.track_id}
          className="absolute rounded-md border-2 border-white/70 pointer-events-none transition-all duration-75 ease-out"
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

      {/* Connection status overlay */}
      {status !== "live" && videoStream && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950/50 backdrop-blur-sm">
          <span className="text-xs font-medium text-white/80">
            {status === "connecting" ? "Đang kết nối…" : "Mất kết nối"}
          </span>
        </div>
      )}
    </div>
  );
}
