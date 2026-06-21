"use client";

import { useViewer } from "../hooks/useViewer";
import { getTrackBadge } from "../lib/trackBadge";

export default function CameraViewerStream({
  sessionId,
  highlightedTrackId = null,
  framed = true,
  compact = false,
  fullHeight = false,
}) {
  const { canvasRef, wsStatus, customers, frameSize } = useViewer(sessionId);

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

  const faces = customers
    .filter((c) => Array.isArray(c.bbox) && c.bbox.length === 4)
    .map((c) => {
      const [x1, y1, x2, y2] = c.bbox;
      return {
        ...c,
        left: (x1 / frameSize.width) * 100,
        top: (y1 / frameSize.height) * 100,
        width: ((x2 - x1) / frameSize.width) * 100,
        height: ((y2 - y1) / frameSize.height) * 100,
      };
    });

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
            <span className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${statusDot}`} />
              <span className="text-sm font-medium text-slate-600">
                {statusLabel} ({sessionId})
              </span>
            </span>
          </div>
          <span className="inline-flex items-center rounded-full bg-indigo-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.25em] text-indigo-600">
            Remote Feed
          </span>
        </div>
      ) : null}

      {/* ── Video Canvas + overlays ── */}
      <div className={`relative bg-slate-950 flex-1 min-h-0 flex items-center justify-center ${compact || fullHeight ? "h-full" : ""}`}>
        <canvas
          ref={canvasRef}
          className={
            compact || fullHeight
              ? "h-full min-h-0 w-full object-contain bg-slate-900"
              : "aspect-[16/10] h-auto min-h-[180px] w-full object-contain bg-slate-900 sm:min-h-[260px] md:min-h-[320px] lg:min-h-[360px]"
          }
        />

        {/* Bounding box overlays */}
        <div className="pointer-events-none absolute inset-0">
          {faces.map((face, i) => {
            const isHl = highlightedTrackId === face.track_id;
            const badge = getTrackBadge(face.track_id);
            const symbol = badge.symbol;
            const theme = badge.theme;

            return (
              <div
                key={face.track_id || i}
                className={`absolute rounded-2xl border-2 bg-white/5 backdrop-blur-[1px] transition-all duration-100 ease-linear ${
                  isHl
                    ? "border-white shadow-[0_0_0_4px_rgba(255,255,255,0.35)]"
                    : face.detected
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
                {theme && symbol && (
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
      </div>
    </div>
  );
}
