import { useEffect, useRef, useState } from "react";
import { useCamera } from "../hooks/useCamera";
import { useLocalFaceDetector } from "../hooks/useLocalFaceDetector";
import { useVideoBbox } from "../hooks/useVideoBbox";
import HudCard from "./HudCard";
import { formatCustomerDisplayId, getCustomerDisplayName } from "../lib/customerCode";
import { useApp } from "../context/AppContext";




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
  onCustomerClick = null,
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
    sendCrop,
    edgeSettings,
    faceImagesRef,
  } = useCamera(cameraId);

  const { t, lang } = useApp();
  const mapBbox = useVideoBbox(videoRef, frameSize.width, frameSize.height);
  const localFaces = useLocalFaceDetector(videoRef);
  const [hoveredTrackId, setHoveredTrackId] = useState(null);
  const hoverTimeoutRef = useRef(null);

  const handleFaceMouseEnter = (id) => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
    setHoveredTrackId(id);
  };

  const handleFaceMouseLeave = () => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
    }
    hoverTimeoutRef.current = setTimeout(() => {
      setHoveredTrackId(null);
    }, 350);
  };

  // Lift customers + frameSize to parent whenever they change
  useEffect(() => {
    // Attach base64 crop image to each customer for UI avatar
    const enrichedCustomers = customers.map(c => ({
       ...c,
       faceImage: faceImagesRef.current[c.local_track_id] || null
    }));
    onCustomersChange?.(enrichedCustomers, frameSize);
  }, [customers, frameSize, onCustomersChange, faceImagesRef]);

  const lastSendTimeRef = useRef({});

  // 1. Trigger crop sending for tracked faces
  useEffect(() => {
    const now = Date.now();
    localFaces.forEach(face => {
      // Skip edge faces or incomplete faces
      if (face.isGoodQuality === false) {
        return;
      }

      // Adaptive throttle: Send 4 FPS (250ms) while identifying; relax to 1.5s once recognized
      const backendMatch = customers.find(c => c.local_track_id === face.local_track_id);
      const isConfirmed = backendMatch && backendMatch.id && backendMatch.customer_status !== "extracting" && backendMatch.name !== "Đang nhận diện..." && backendMatch.name !== "Identifying...";
      const sendInterval = isConfirmed ? (edgeSettings?.edge_send_interval_ms || 1500) : 250;

      const lastSend = lastSendTimeRef.current[face.local_track_id] || 0;
      // Send crop if not sent in the configured interval
      if (now - lastSend > sendInterval) {
        sendCrop(face);
        lastSendTimeRef.current[face.local_track_id] = now;
      }
    });
  }, [localFaces, sendCrop, edgeSettings, customers]);

  // 2. Merge local faces with backend profiles
  const mergedFaces = localFaces.map((localFace, i) => {
    // Find backend profile by local_track_id
    const backendMatch = customers.find(c => c.local_track_id === localFace.local_track_id);
    
    const lx = (localFace.left / 100) * frameSize.width;
    const ly = (localFace.top / 100) * frameSize.height;
    const lw = (localFace.width / 100) * frameSize.width;
    const lh = (localFace.height / 100) * frameSize.height;
    const mappedLocal = mapBbox(lx, ly, lw, lh);

    return {
      ...localFace,
      ...mappedLocal,
      id: localFace.local_track_id,
      backendMatch: backendMatch || null,
    };
  });

  const unmatchedBackendFaces = [];

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


            {/* Camera selector */}
            <select
              value={selectedDeviceId}
              onChange={(e) => setSelectedDeviceId(e.target.value)}
              className="w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2.5 text-sm text-slate-700 dark:text-slate-200 outline-none transition focus:border-indigo-300 sm:w-auto sm:min-w-[180px] lg:min-w-[220px]"
            >
              <option value="">{t("integrated_camera") || "Integrated Camera"}</option>
              {devices.map((device, i) => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label || `Camera ${i + 1}`}
                </option>
              ))}
            </select>
          </div>

          <span className="inline-flex items-center rounded-full bg-emerald-50 dark:bg-emerald-950/60 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.25em] text-emerald-600 dark:text-emerald-400">
            {t("live_feed")}
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

        {/* Bounding box overlays with UNK tag and HUD Card on Hover */}
        <div className="absolute inset-0 pointer-events-none">
          {mergedFaces.map((face) => {
            const isHovered =
              hoveredTrackId === face.id ||
              (Boolean(hoveredTrackId) && mergedFaces.length === 1);

            const displayCustomerId = formatCustomerDisplayId(face.backendMatch, face);
            const customerName = getCustomerDisplayName(face.backendMatch, face, lang);

            const isResolved = Boolean(displayCustomerId);
            const isIdentified = Boolean(
              isResolved &&
                face.backendMatch &&
                face.backendMatch.detected &&
                face.backendMatch.customer_type !== "guest" &&
                face.backendMatch.name &&
                face.backendMatch.name.trim() !== "" &&
                face.backendMatch.name !== "Guest" &&
                face.backendMatch.name !== "Khách mới"
            );

            // Smart Popover Direction & Alignment
            const direction = face.left < 50 ? "right" : "left";
            const verticalAlign = face.top > 50 ? "bottom" : "top";

            return (
              <div
                key={face.id}
                className="absolute pointer-events-auto transition-all duration-75 ease-out cursor-pointer"
                style={{
                  left: `${face.left}%`,
                  top: `${face.top}%`,
                  width: `${Math.max(face.width, 6)}%`,
                  height: `${Math.max(face.height, 8)}%`,
                }}
                onMouseEnter={() => handleFaceMouseEnter(face.id)}
                onMouseLeave={handleFaceMouseLeave}
                onClick={(e) => {
                  e.stopPropagation();
                  if (onCustomerClick) {
                    const targetCustomer = face.backendMatch || {
                      id: face.id,
                      track_id: face.id,
                      name: customerName,
                      customer_type: "guest",
                    };
                    onCustomerClick(targetCustomer);
                  }
                }}
              >
                {/* ── Bounding Box Frame: Amber khi đang nhận diện, Xanh lục khi có hồ sơ, Xanh biển khi đã nhận diện khách vãng lai ── */}
                <div
                  className={`w-full h-full rounded-sm border transition-all duration-150 relative ${
                    !isResolved
                      ? isHovered
                        ? "border-amber-300 bg-amber-500/15 shadow-[0_0_14px_rgba(245,158,11,0.5)]"
                        : "border-amber-400/80 bg-amber-500/5 hover:border-amber-300 hover:bg-amber-500/10"
                      : isIdentified
                      ? isHovered
                        ? "border-emerald-300 bg-emerald-500/15 shadow-[0_0_16px_rgba(52,211,153,0.55)]"
                        : "border-emerald-400 bg-emerald-500/10 shadow-[0_0_10px_rgba(52,211,153,0.35)] hover:border-emerald-300"
                      : isHovered
                      ? "border-sky-300 bg-sky-500/10 shadow-[0_0_12px_rgba(56,189,248,0.45)]"
                      : "border-sky-400/80 bg-sky-500/5 hover:border-sky-300 hover:bg-sky-500/10"
                  }`}
                >
                  {/* 4 Corner Sci-Fi Brackets */}
                  <div
                    className={`absolute -top-[2px] -left-[2px] w-2.5 h-2.5 border-t-2 border-l-2 ${
                      !isResolved
                        ? "border-amber-400"
                        : isIdentified
                        ? "border-emerald-300"
                        : "border-sky-300"
                    }`}
                  />
                  <div
                    className={`absolute -top-[2px] -right-[2px] w-2.5 h-2.5 border-t-2 border-r-2 ${
                      !isResolved
                        ? "border-amber-400"
                        : isIdentified
                        ? "border-emerald-300"
                        : "border-sky-300"
                    }`}
                  />
                  <div
                    className={`absolute -bottom-[2px] -left-[2px] w-2.5 h-2.5 border-b-2 border-l-2 ${
                      !isResolved
                        ? "border-amber-400"
                        : isIdentified
                        ? "border-emerald-300"
                        : "border-sky-300"
                    }`}
                  />
                  <div
                    className={`absolute -bottom-[2px] -right-[2px] w-2.5 h-2.5 border-b-2 border-r-2 ${
                      !isResolved
                        ? "border-amber-400"
                        : isIdentified
                        ? "border-emerald-300"
                        : "border-sky-300"
                    }`}
                  />

                  {/* ── Top Badge: Hiện "ĐANG NHẬN DIỆN..." khi chưa lưu vector, chỉ đổi sang LN/MN/LL/LC khi đã lưu và nhận diện được ── */}
                  <div className="absolute -top-6 left-0 flex items-center">
                    {!isResolved ? (
                      <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm bg-slate-950/90 border border-amber-400/80 text-amber-300 text-[10px] font-mono font-bold tracking-wider shadow-[0_0_8px_rgba(245,158,11,0.35)] backdrop-blur-sm animate-pulse">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
                        {t("identifying")}
                      </div>
                    ) : !isIdentified ? (
                      <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm bg-slate-950/85 border border-sky-400/70 text-sky-300 text-[10px] font-mono font-bold tracking-wider shadow-[0_0_8px_rgba(56,189,248,0.3)] backdrop-blur-sm">
                        <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
                        {displayCustomerId}
                      </div>
                    ) : (
                      <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm bg-slate-950/85 border border-emerald-400/80 text-emerald-200 text-[10px] font-mono font-bold tracking-wider shadow-[0_0_8px_rgba(52,211,153,0.4)] backdrop-blur-sm">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        {customerName}
                        <span className="text-emerald-300/80 text-[9px] font-mono">
                          [{displayCustomerId}]
                        </span>
                        {face.backendMatch?.loyalty_tier && (
                          <span className="text-amber-400 text-[9px] font-extrabold uppercase">
                            • {face.backendMatch.loyalty_tier}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* ── HUD DATA Card (hiện khi hover vào bbox) ── */}
                {isHovered && (
                  <HudCard
                    customer={face.backendMatch}
                    face={face}
                    direction={direction}
                    verticalAlign={verticalAlign}
                    onMouseEnter={() => handleFaceMouseEnter(face.id)}
                    onMouseLeave={handleFaceMouseLeave}
                    onEditProfile={(customer, face) => {
                      if (onCustomerClick) {
                        const targetCustomer = customer || {
                          id: face.id,
                          track_id: face.id,
                          name: customerName,
                          customer_type: "guest",
                        };
                        onCustomerClick(targetCustomer);
                      }
                    }}
                  />
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
