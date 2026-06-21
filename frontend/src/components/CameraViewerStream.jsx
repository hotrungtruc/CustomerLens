"use client";

import { useEffect, useRef } from "react";
import { useViewer } from "../hooks/useViewer";
import { getTrackBadge } from "../lib/trackBadge";

export default function CameraViewerStream({
  sessionId,
  highlightedTrackId = null,
  framed = true,
  compact = false,
  fullHeight = false,
}) {
  const { wsStatus, customers, frameSize, imageUrl } = useViewer(sessionId);
  const canvasRef = useRef(null);

  // Draw bounding boxes when customers or frameSize changes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    customers.forEach((c) => {
      if (!Array.isArray(c.bbox) || c.bbox.length !== 4) return;
      const [x1, y1, x2, y2] = c.bbox;
      const w = x2 - x1;
      const h = y2 - y1;

      // Calculate scale to map backend coordinates to canvas resolution
      const scaleX = canvas.width / frameSize.width;
      const scaleY = canvas.height / frameSize.height;

      const cx1 = x1 * scaleX;
      const cy1 = y1 * scaleY;
      const cw = w * scaleX;
      const ch = h * scaleY;

      const badge = getTrackBadge(c.track_id);
      const isHighlighted = c.track_id === highlightedTrackId;

      const primaryColor = c.is_guest ? "rgba(100,116,139,1)" : "rgba(16,185,129,1)";
      const glowColor = c.is_guest ? "rgba(100,116,139,0.3)" : "rgba(16,185,129,0.3)";

      ctx.lineWidth = isHighlighted ? 4 : 3;
      ctx.strokeStyle = primaryColor;

      // Glow effect
      ctx.shadowColor = glowColor;
      ctx.shadowBlur = 10;
      ctx.strokeRect(cx1, cy1, cw, ch);
      ctx.shadowBlur = 0; // reset

      // Draw Badge background
      ctx.fillStyle = primaryColor;
      ctx.beginPath();
      ctx.roundRect(cx1 + cw / 2 - 12, cy1 - 12, 24, 24, 12);
      ctx.fill();

      // Text inside badge
      ctx.fillStyle = "#fff";
      ctx.font = "bold 11px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(badge, cx1 + cw / 2, cy1);

      // Name label
      const label = c.name || (c.is_guest ? "Khách mời" : `CLIENT_${c.id}`);
      ctx.font = "600 12px Inter, sans-serif";
      const metrics = ctx.measureText(label);
      const tw = metrics.width + 12;
      ctx.fillStyle = "rgba(0,0,0,0.6)";
      ctx.beginPath();
      ctx.roundRect(cx1 + cw / 2 - tw / 2, cy1 + ch + 8, tw, 22, 6);
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.fillText(label, cx1 + cw / 2, cy1 + ch + 19);
    });
  }, [customers, frameSize, highlightedTrackId]);

  const statusLabel =
    wsStatus === "live"
      ? "Trực tiếp"
      : wsStatus === "connecting"
        ? "Đang kết nối…"
        : wsStatus === "error"
          ? "Lỗi kết nối"
          : "Mất kết nối";

  const statusDot =
    wsStatus === "live"
      ? "bg-emerald-500"
      : wsStatus === "connecting"
        ? "bg-amber-400 animate-pulse"
        : "bg-rose-500 animate-pulse";

  return (
    <div
      className={
        framed
          ? "h-full overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_40px_rgba(15,23,42,0.08)] flex flex-col"
          : "h-full overflow-hidden bg-white flex flex-col"
      }
    >
      {/* Header bar */}
      {!compact ? (
        <div className="shrink-0 flex items-center justify-between px-5 py-4 border-b border-slate-100 bg-white/50 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-blue-100 shadow-sm">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15.6 11.6L22 7v10l-6.4-4.5v-1zM4 5h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7c0-1.1.9-2 2-2z" />
              </svg>
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-800">
                Thiết bị: {sessionId}
              </h2>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`h-2 w-2 rounded-full ${statusDot}`} />
                <span className="text-[13px] font-semibold tracking-wide text-slate-500">
                  {statusLabel}
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Viewport */}
      <div className={`relative flex-1 w-full bg-slate-950 overflow-hidden ${fullHeight ? "" : "min-h-[300px]"}`}>
        {/* Placeholder if no image yet */}
        {!imageUrl && wsStatus !== "live" && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm font-medium">
            {statusLabel}
          </div>
        )}

        {imageUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl}
            alt="Camera Stream"
            className="absolute inset-0 w-full h-full object-contain"
          />
        )}

        {/* Canvas overlay */}
        <canvas
          ref={canvasRef}
          width={frameSize.width || 640}
          height={frameSize.height || 360}
          className="absolute inset-0 w-full h-full object-contain pointer-events-none"
        />

        {/* Compact Mode Overlay Status */}
        {compact && (
          <div className="absolute top-2 left-2 z-20 flex items-center gap-1.5 rounded-full bg-slate-900/60 px-2.5 py-1 backdrop-blur-md border border-white/10 shadow-sm">
            <span className={`h-1.5 w-1.5 rounded-full ${statusDot}`} />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-white/90">
              {statusLabel}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
