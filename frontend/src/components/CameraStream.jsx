"use client";

import { useEffect } from "react";
import { useCamera } from "../hooks/useCamera";
import { getTrackBadge } from "./trackBadge";

/**
 * CameraStream — live webcam feed with bounding-box overlays.
 *
 * Props:
 *   sessionId         — unique ID for this camera session (backend creates its own CameraState)
 *   highlightedTrackId — track_id to highlight with a white ring
 *   framed            — wrap in a card border/shadow
 *   onCustomersChange — optional callback(customers, frameSize) for parent state lifting
 */
export default function CameraStream({
  sessionId,
  highlightedTrackId = null,
  framed = true,
  onCustomersChange = null,
}) {
  const {
    videoRef,
    canvasRef,
    devices,
    selectedDeviceId,
    setSelectedDeviceId,
    wsStatus,
    customers,
    frameSize,
    cameraError,
  } = useCamera(sessionId);

  // Lift customers + frameSize to parent whenever they change
  useEffect(() => {
    onCustomersChange?.(customers, frameSize);
  }, [customers, frameSize, onCustomersChange]);

  const statusLabel =
    wsStatus === "live"
      ? "Camera live"
      : wsStatus === "connecting"
      ? "Connecting…"
      : wsStatus === "error"
      ? "Connection error"
      : "Reconnecting…";

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
          ? "overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_40px_rgba(15,23,42,0.08)]"
          : "overflow-hidden bg-white"
      }
    >
      {/* ── Header bar ── */}
      <div className="flex flex-col gap-3 border-b border-slate-200/80 px-4 py-4 text-sm text-slate-500 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          {/* Status dot + label */}
          <span className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${statusDot}`} />
            <span className="text-sm font-medium text-slate-600">{statusLabel}</span>
          </span>

          {/* Camera selector */}
          <select
            value={selectedDeviceId}
            onChange={(e) => setSelectedDeviceId(e.target.value)}
            className="min-w-[240px] rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none transition focus:border-indigo-300"
          >
            <option value="">Integrated Camera</option>
            {devices.map((device, i) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label || `Camera ${i + 1}`}
              </option>
            ))}
          </select>
        </div>

        <span className="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.25em] text-emerald-600">
          Live feed
        </span>
      </div>

      {/* ── Video + overlays ── */}
      <div className="relative bg-slate-950">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="aspect-[16/10] h-auto min-h-[220px] w-full object-cover sm:min-h-[340px] md:min-h-[420px]"
        />

        {/* Bounding box overlays */}
        <div className="pointer-events-none absolute inset-0">
          {customers
            .filter((c) => Array.isArray(c.bbox) && c.bbox.length === 4)
            .map((c) => {
              const [x1, y1, x2, y2] = c.bbox;
              const left   = (x1 / frameSize.width)  * 100;
              const top    = (y1 / frameSize.height) * 100;
              const width  = ((x2 - x1) / frameSize.width)  * 100;
              const height = ((y2 - y1) / frameSize.height) * 100;
              const isHl   = highlightedTrackId === c.track_id;
              const { symbol, theme } = getTrackBadge(c.track_id);

              return (
                <div
                  key={`overlay-${c.tile_id}`}
                  className={`absolute rounded-2xl border-2 bg-white/5 backdrop-blur-[1px] ${
                    isHl
                      ? "border-white shadow-[0_0_0_4px_rgba(255,255,255,0.35)]"
                      : "border-white/80"
                  }`}
                  style={{
                    left:   `${left}%`,
                    top:    `${top}%`,
                    width:  `${Math.max(width, 6)}%`,
                    height: `${Math.max(height, 8)}%`,
                  }}
                >
                  <div
                    className={`-mt-3 ml-2 inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white ring-2 ring-white/40 ${theme.base} ${theme.ring} ${
                      isHl ? "scale-110" : ""
                    }`}
                  >
                    {symbol}
                  </div>
                </div>
              );
            })}
        </div>

        {/* Hidden capture canvas */}
        <canvas ref={canvasRef} className="hidden" />

        {/* Camera / WS error banner */}
        {cameraError ? (
          <div className="absolute inset-x-4 bottom-4 rounded-2xl border border-rose-200 bg-rose-50/95 px-4 py-3 text-sm text-rose-600 shadow-lg">
            {cameraError}
          </div>
        ) : null}
      </div>
    </div>
  );
}
