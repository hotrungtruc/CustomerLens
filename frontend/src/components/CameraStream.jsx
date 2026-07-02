"use client";

import { useEffect, useRef } from "react";
import { useCamera } from "../hooks/useCamera";
import { useLocalFaceDetector } from "../hooks/useLocalFaceDetector";
import { useVideoBbox } from "../hooks/useVideoBbox";
import { getTrackBadge } from "../lib/trackBadge";

// IoU matching (Intersection over Union)
function calculateIoU(boxA, boxB) {
  const xA = Math.max(boxA.left, boxB.left);
  const yA = Math.max(boxA.top, boxB.top);
  const xB = Math.min(boxA.left + boxA.width, boxB.left + boxB.width);
  const yB = Math.min(boxA.top + boxA.height, boxB.top + boxB.height);
  const interArea = Math.max(0, xB - xA) * Math.max(0, yB - yA);
  if (interArea === 0) return 0;
  const boxAArea = boxA.width * boxA.height;
  const boxBArea = boxB.width * boxB.height;
  return interArea / (boxAArea + boxBArea - interArea);
}

/**
 * CameraStream — live webcam feed with bounding-box overlays.
 *
 * Props:
 *   cameraId          — stable camera identity resolved by the backend
 *   highlightedTrackId — track_id to highlight with a white ring
 *   framed            — wrap in a card border/shadow
 *   fullHeight        — force container to full height
 *   onCustomersChange — optional callback(customers, frameSize) for parent state lifting
 */
export default function CameraStream({
  cameraId,
  highlightedTrackId = null,
  framed = true,
  compact = false,
  fullHeight = false,
  onCustomersChange = null,
}) {
  const {
    videoRef,
    canvasRef,
    devices,
    selectedDeviceId,
    setSelectedDeviceId,
    wsStatus,
    takeOver,
    customers,
    frameSize,
    cameraError,
  } = useCamera(cameraId);

  const mapBbox = useVideoBbox(videoRef, frameSize.width, frameSize.height);
  const localFaces = useLocalFaceDetector(videoRef);

  // Lift customers + frameSize to parent whenever they change
  useEffect(() => {
    onCustomersChange?.(customers, frameSize);
  }, [customers, frameSize, onCustomersChange]);

  // Transform backend customers into percentage boxes
  const backendFaces = customers
    .filter((c) => Array.isArray(c.bbox) && c.bbox.length === 4)
    .map((c) => {
      const [x1, y1, x2, y2] = c.bbox;
      const mapped = mapBbox(x1, y1, x2 - x1, y2 - y1);
      return {
        ...c,
        left: mapped.left,
        top: mapped.top,
        width: mapped.width,
        height: mapped.height,
      };
    });

  const prevLocalFacesRef = useRef([]);

  // Hybrid Tracking: Merge local faces with backend labels
  const matchedBackendIds = new Set();
  const mergedFaces = localFaces.map((localFace, i) => {
    let bestMatch = null;
    let bestIoU = 0;
    
    // 1. Try to match with CURRENT backend faces
    backendFaces.forEach((backendFace) => {
      const iou = calculateIoU(localFace, backendFace);
      if (iou > 0.2 && iou > bestIoU) {
        bestIoU = iou;
        bestMatch = backendFace;
      }
    });

    // 2. If no current match, try to inherit from PREVIOUS local face
    if (!bestMatch) {
      let bestPrevLocalMatch = null;
      let bestPrevIoU = 0;
      prevLocalFacesRef.current.forEach((prevLocalFace) => {
        const iou = calculateIoU(localFace, prevLocalFace);
        if (iou > 0.3 && iou > bestPrevIoU) {
          bestPrevIoU = iou;
          bestPrevLocalMatch = prevLocalFace;
        }
      });
      if (bestPrevLocalMatch && bestPrevLocalMatch.backendMatch) {
         bestMatch = bestPrevLocalMatch.backendMatch;
      }
    }
    
    if (bestMatch) {
      matchedBackendIds.add(bestMatch.track_id);
    }
    
    // localFace returns percentage of native video width, let's map it via mapBbox 
    // by pretending it's an absolute coordinate.
    const lx = (localFace.left / 100) * frameSize.width;
    const ly = (localFace.top / 100) * frameSize.height;
    const lw = (localFace.width / 100) * frameSize.width;
    const lh = (localFace.height / 100) * frameSize.height;
    const mappedLocal = mapBbox(lx, ly, lw, lh);

    return {
      ...localFace,
      ...mappedLocal,
      id: bestMatch ? bestMatch.track_id : `local-${i}`,
      backendMatch: bestMatch,
    };
  });

  // Update prevLocalFacesRef for next frame
  useEffect(() => {
    prevLocalFacesRef.current = mergedFaces;
  }, [mergedFaces]);

  const unmatchedBackendFaces = backendFaces.filter(
    (bf) => !matchedBackendIds.has(bf.track_id)
  );

  const statusLabel =
    wsStatus === "live"
      ? "Camera live"
      : wsStatus === "connecting"
        ? "Connecting…"
        : wsStatus === "taken_over"
          ? "Opened elsewhere"
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
          ? "h-full overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_40px_rgba(15,23,42,0.08)] flex flex-col"
          : "h-full overflow-hidden bg-white flex flex-col"
      }
    >
      {/* ── Header bar ── */}
      {!compact ? (
        <div className="flex flex-col gap-3 border-b border-slate-200/80 px-4 py-4 text-sm text-slate-500 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            {/* Status dot + label */}
            <span className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${statusDot}`} />
              <span className="text-sm font-medium text-slate-600">
                {statusLabel}
              </span>
            </span>

            {(wsStatus === "disconnected" ||
              wsStatus === "error" ||
              wsStatus === "taken_over") && (
              <button
                type="button"
                onClick={takeOver}
                className="rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700 hover:bg-amber-100"
              >
                Tiếp quản camera
              </button>
            )}

            {/* Camera selector */}
            <select
              value={selectedDeviceId}
              onChange={(e) => setSelectedDeviceId(e.target.value)}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none transition focus:border-indigo-300 sm:w-auto sm:min-w-[180px] lg:min-w-[220px]"
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
      ) : null}

      {/* ── Video + overlays ── */}
      <div className={`relative bg-slate-950 flex-1 min-h-0 ${compact || fullHeight ? "h-full" : ""}`}>
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={
            compact || fullHeight
              ? "h-full min-h-0 w-full object-cover"
              : "aspect-[16/10] h-auto min-h-[180px] w-full object-cover sm:min-h-[260px] md:min-h-[320px] lg:min-h-[360px]"
          }
        />

        {/* Bounding box overlays */}
        <div className="pointer-events-none absolute inset-0">
          {mergedFaces.map((face) => {
            const isHl = face.backendMatch && highlightedTrackId === face.backendMatch.track_id;
            
            let symbol = null;
            let theme = null;
            if (face.backendMatch) {
               const badge = getTrackBadge(face.backendMatch.track_id);
               symbol = badge.symbol;
               theme = badge.theme;
            }

            return (
              <div
                key={face.id}
                className={`absolute rounded-2xl border-2 bg-white/5 backdrop-blur-[1px] transition-all duration-100 ease-linear ${
                  isHl
                    ? "border-white shadow-[0_0_0_4px_rgba(255,255,255,0.35)]"
                    : face.backendMatch?.detected
                      ? "border-white/80"
                      : "border-slate-300"
                }`}
                style={{
                  left: `${face.left}%`,
                  top: `${face.top}%`,
                  width: `${Math.max(face.width, 6)}%`,
                  height: `${Math.max(face.height, 8)}%`,
                }}
              >
                {face.backendMatch && theme && symbol && (
                  <div
                    className={`-mt-3 ml-2 inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white ring-2 ring-white/40 ${theme.base} ${theme.ring} ${
                      isHl ? "scale-110" : ""
                    }`}
                  >
                    {symbol}
                  </div>
                )}
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
