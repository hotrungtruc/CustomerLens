import { useEffect, useRef, useState } from "react";
import { useCamera } from "../hooks/useCamera";
import { useLocalFaceDetector } from "../hooks/useLocalFaceDetector";
import { useVideoBbox } from "../hooks/useVideoBbox";
import HudCard from "./HudCard";
import {
  formatCustomerDisplayId,
  getCustomerDisplayName,
  getCustomerSegment,
  getLocalizedSegment,
} from "../lib/customerCode";
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
  const [pinnedFace, setPinnedFace] = useState(null);
  const hoverTimeoutRef = useRef(null);
  const fileInputRef = useRef(null);
  const [customVideoLabel, setCustomVideoLabel] = useState("");

  // Close pinned inspection modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        setPinnedFace(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

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
      // Skip edge faces, low quality, or coasting/predicted frames
      if (face.isGoodQuality === false || face.isCoasting) {
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
    // Find backend profile strictly by local_track_id or track_id
    const backendMatch = customers.find(c => 
      String(c.local_track_id) === String(localFace.local_track_id) ||
      String(c.track_id) === String(localFace.local_track_id)
    );
    
    const lx = (localFace.left / 100) * frameSize.width;
    const ly = (localFace.top / 100) * frameSize.height;
    const lw = (localFace.width / 100) * frameSize.width;
    const lh = (localFace.height / 100) * frameSize.height;
    const mappedLocal = mapBbox(lx, ly, lw, lh);

    const faceImage = faceImagesRef.current[localFace.local_track_id] || backendMatch?.faceImage || null;

    return {
      ...localFace,
      ...mappedLocal,
      id: localFace.local_track_id,
      faceImage,
      backendMatch: backendMatch || null,
    };
  });

  // Dynamically resolve customer data for the pinned inspection target
  const pinnedCustomer = pinnedFace
    ? (customers.find((c) => c.local_track_id === pinnedFace.id) || pinnedFace.backendMatch)
    : null;

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
        <div className="relative z-10 flex flex-col gap-3 border-b border-slate-200/80 bg-white dark:bg-slate-900 px-4 py-4 text-sm text-slate-500 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            {/* Status dot + label */}
            <div className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${statusDot}`} />
              <span className="text-sm font-medium text-slate-600 dark:text-slate-300">
                {statusLabel}
              </span>
              {wsStatus === "taken_over" && (
                <button
                  type="button"
                  onClick={takeOver}
                  className="ml-1 px-2.5 py-0.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold shadow-sm transition animate-pulse flex items-center gap-1"
                >
                  ⚡ Chiếm quyền
                </button>
              )}
            </div>

            {/* Camera / Video stream selector */}
            <select
              value={selectedDeviceId}
              onChange={(e) => {
                const val = e.target.value;
                if (val === "__upload__") {
                  fileInputRef.current?.click();
                } else {
                  if (val !== "sample_video" && !val.startsWith("blob:")) {
                    setCustomVideoLabel("");
                  }
                  setSelectedDeviceId(val);
                }
              }}
              className="w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2.5 text-sm text-slate-700 dark:text-slate-200 outline-none transition focus:border-indigo-300 sm:w-auto sm:min-w-[180px] lg:min-w-[220px]"
            >
              <optgroup label="📹 Webcam / Camera">
                <option value="">{t("integrated_camera") || "Integrated Camera"}</option>
                {devices.map((device, i) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.label || `Camera ${i + 1}`}
                  </option>
                ))}
              </optgroup>
              <optgroup label="🎬 YTF Celebrity Test Videos (Cận cảnh / End-to-End)">
                <option value="/videos/Bill_Clinton_0.mp4">🌟 Bill Clinton #0 (Đăng ký mới)</option>
                <option value="/videos/Bill_Clinton_1.mp4">🔄 Bill Clinton #1 (Kiểm tra nhận diện lại)</option>
                <option value="/videos/Chris_Rock_0.mp4">🌟 Chris Rock #0</option>
                <option value="/videos/Chris_Rock_1.mp4">🔄 Chris Rock #1</option>
                <option value="/videos/Angelina_Jolie_2.mp4">🌟 Angelina Jolie #2</option>
                <option value="/videos/Angelina_Jolie_3.mp4">🔄 Angelina Jolie #3</option>
                <option value="/videos/Beyonce_Knowles_0.mp4">🌟 Beyonce Knowles #0</option>
                <option value="/videos/Beyonce_Knowles_3.mp4">🔄 Beyonce Knowles #3</option>
                <option value="/videos/Conan_OBrien_0.mp4">🌟 Conan O'Brien #0</option>
                <option value="/videos/Conan_OBrien_1.mp4">🔄 Conan O'Brien #1</option>
                <option value="/videos/Carrie-Anne_Moss_0.mp4">🌟 Carrie-Anne Moss #0</option>
                <option value="/videos/Carrie-Anne_Moss_1.mp4">🔄 Carrie-Anne Moss #1</option>
                <option value="/videos/Charlize_Theron_1.mp4">🌟 Charlize Theron #1</option>
                <option value="/videos/Charlize_Theron_3.mp4">🔄 Charlize Theron #3</option>
                <option value="/videos/Aaron_Eckhart_0.mp4">👤 Aaron Eckhart #0</option>
                <option value="/videos/Adam_Sandler_0.mp4">👤 Adam Sandler #0</option>
                <option value="/videos/Cameron_Diaz_2.mp4">👤 Cameron Diaz #2</option>
                <option value="/videos/Cindy_Crawford_0.mp4">👤 Cindy Crawford #0</option>
                <option value="sample_video">🚶 Phố đi bộ CCTV (assets/test_video.mp4)</option>
                {selectedDeviceId && selectedDeviceId.startsWith("blob:") && (
                  <option value={selectedDeviceId}>
                    📁 {customVideoLabel ? `File: ${customVideoLabel}` : "File video đã tải"}
                  </option>
                )}
                <option value="__upload__">📁 Tải lên file video (.mp4)...</option>
              </optgroup>
            </select>

            <input
              type="file"
              ref={fileInputRef}
              accept="video/mp4,video/webm"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  const url = URL.createObjectURL(file);
                  setCustomVideoLabel(file.name);
                  setSelectedDeviceId(url);
                }
              }}
            />
          </div>

          <span className={`inline-flex items-center rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.25em] ${
            cameraError
              ? "bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400"
              : selectedDeviceId === "sample_video" || selectedDeviceId?.startsWith("blob:") || selectedDeviceId?.endsWith(".mp4")
              ? "bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400"
              : "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400"
          }`}>
            {cameraError ? "⚠️ CAMERA LỖI" : selectedDeviceId === "sample_video" || selectedDeviceId?.startsWith("blob:") || selectedDeviceId?.endsWith(".mp4") ? "🎬 VIDEO STREAM" : t("live_feed")}
          </span>
        </div>
      ) : null}

      {/* ── Video + overlays ── */}
      <div className={`relative bg-slate-950 flex-1 min-h-0 overflow-hidden ${compact || fullHeight ? "h-full" : ""}`}>
        {cameraError && (
          <div className="absolute top-4 left-4 right-4 z-40 p-4 bg-rose-950/90 border border-rose-500/60 backdrop-blur-md rounded-2xl shadow-2xl flex items-center justify-between gap-4 text-sm text-rose-200">
            <div className="flex items-center gap-3">
              <span className="text-2xl shrink-0">⚠️</span>
              <div>
                <p className="font-semibold text-rose-100">Không thể kết nối camera vật lý</p>
                <p className="text-xs text-rose-300 mt-0.5">{cameraError}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => setSelectedDeviceId("sample_video")}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold shadow transition"
              >
                Dùng video mẫu
              </button>
            </div>
          </div>
        )}
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
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
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

            const safeLeft = Math.max(0, Math.min(96, face.left));
            const safeTop = Math.max(0, Math.min(96, face.top));
            const safeWidth = Math.max(4, Math.min(100 - safeLeft, face.width));
            const safeHeight = Math.max(4, Math.min(100 - safeTop, face.height));

            return (
              <div
                key={face.id}
                className={`absolute pointer-events-auto cursor-pointer select-none will-change-transform ${face.isCoasting ? "opacity-85" : "opacity-100"}`}
                style={{
                  left: `${safeLeft}%`,
                  top: `${safeTop}%`,
                  width: `${safeWidth}%`,
                  height: `${safeHeight}%`,
                }}
                onMouseEnter={() => handleFaceMouseEnter(face.id)}
                onMouseLeave={handleFaceMouseLeave}
                onClick={(e) => {
                  e.stopPropagation();
                  // Directly open edit / profile for this face
                  if (onCustomerClick) {
                    const targetCustomer = face.backendMatch || {
                      id: face.id,
                      track_id: face.id,
                      local_track_id: face.local_track_id,
                      name: customerName,
                      faceImage: face.faceImage,
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

                  {/* ── Top Badge: Ô chứa gương mặt MediaPipe + Thẻ ID / Tên ── */}
                  <div className={`absolute flex items-center gap-1.5 ${face.top < 7 ? "top-1 left-1 z-10" : `-top-8 ${face.left > 75 ? "right-0" : "left-0"}`}`}>
                    {/* MediaPipe Face Thumbnail Box */}
                    {face.faceImage && (
                      <div className="relative w-7 h-7 rounded border border-cyan-400/80 overflow-hidden bg-slate-950 shrink-0 shadow-[0_0_10px_rgba(34,211,238,0.5)]">
                        <img
                          src={face.faceImage}
                          alt="Face Crop"
                          className="w-full h-full object-cover"
                        />
                        <div className="absolute inset-0 bg-cyan-400/10 pointer-events-none" />
                        <div className="absolute bottom-0 right-0 w-1.5 h-1.5 bg-cyan-400" />
                      </div>
                    )}

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

                {/* ── HUD DATA Card (hiện khi hover vào bbox — chỉ xem thông tin, click bbox để edit) ── */}
                {isHovered && (
                  <HudCard
                    customer={face.backendMatch}
                    face={face}
                    direction={direction}
                    verticalAlign={verticalAlign}
                    onMouseEnter={() => handleFaceMouseEnter(face.id)}
                    onMouseLeave={handleFaceMouseLeave}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* ── Box lớn dừng lại để xem (Biometric Pinned Inspection Modal) ── */}
        {pinnedFace && (
          <div className="absolute top-4 right-4 z-40 w-[350px] max-w-[calc(100%-32px)] select-none animate-in fade-in zoom-in-95 duration-200">
            <div className="relative rounded-2xl border-2 border-cyan-400/90 bg-[#041417]/95 p-4 text-cyan-100 shadow-[0_0_35px_rgba(6,182,212,0.45)] backdrop-blur-xl font-mono">
              {/* Header Tab with Target Lock Status */}
              <div className="flex items-center justify-between border-b border-cyan-500/40 pb-2.5 mb-3">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                  <span className="text-[11px] font-bold uppercase tracking-widest text-cyan-300">
                    🎯 ĐÃ DỪNG LẠI XEM (TARGET LOCKED)
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setPinnedFace(null)}
                  className="px-2 py-0.5 rounded bg-cyan-950/80 hover:bg-rose-500/30 border border-cyan-500/50 hover:border-rose-400 text-cyan-300 hover:text-rose-200 text-xs font-bold transition flex items-center gap-1 cursor-pointer"
                  title="Đóng / Bỏ dừng (Esc)"
                >
                  ✕ Đóng
                </button>
              </div>

              {/* MediaPipe Face + Primary Identification */}
              <div className="flex items-start gap-3.5 mb-3">
                {/* MediaPipe Face Snapshot Frame */}
                <div className="relative w-20 h-20 rounded-xl border-2 border-cyan-400 bg-black overflow-hidden shrink-0 shadow-[0_0_15px_rgba(34,211,238,0.4)]">
                  {pinnedFace.faceImage ? (
                    <img
                      src={pinnedFace.faceImage}
                      alt="MediaPipe Face Snapshot"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-cyan-500 text-xs">
                      No Crop
                    </div>
                  )}
                  {/* Cyber Reticle Overlay */}
                  <div className="absolute inset-0 border border-cyan-400/40 pointer-events-none" />
                  <div className="absolute top-0 left-0 w-2 h-2 border-t-2 border-l-2 border-cyan-300" />
                  <div className="absolute top-0 right-0 w-2 h-2 border-t-2 border-r-2 border-cyan-300" />
                  <div className="absolute bottom-0 left-0 w-2 h-2 border-b-2 border-l-2 border-cyan-300" />
                  <div className="absolute bottom-0 right-0 w-2 h-2 border-b-2 border-r-2 border-cyan-300" />
                </div>

                {/* Identity Info */}
                <div className="flex-1 min-w-0">
                  <div className="text-[9px] text-cyan-400/80 font-bold uppercase tracking-wider mb-0.5">
                    ĐỊNH DANH BIOMETRIC
                  </div>
                  <div className="text-[15px] font-black text-amber-300 truncate drop-shadow-[0_0_8px_rgba(245,158,11,0.5)]">
                    {getCustomerDisplayName(pinnedCustomer, pinnedFace, lang)}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-400 text-cyan-300 text-[11px] font-extrabold tracking-wider">
                      #{formatCustomerDisplayId(pinnedCustomer, pinnedFace) || pinnedFace.id}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-400 text-emerald-300 text-[10px] font-bold">
                      {pinnedCustomer?.customer_type === "guest" ? "Khách vãng lai" : "Hồ sơ đã lưu"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Segmentation & Tier Box */}
              <div className="mb-3 rounded-xl border border-cyan-500/40 bg-cyan-950/40 p-2.5">
                <div className="text-[9px] text-cyan-400/80 uppercase font-bold tracking-wider mb-1 flex items-center justify-between">
                  <span>Phân khúc khách hàng</span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded font-extrabold border ${getLocalizedSegment(getCustomerSegment(pinnedCustomer), lang).badgeColor}`}>
                    [{getLocalizedSegment(getCustomerSegment(pinnedCustomer), lang).code}]
                  </span>
                </div>
                <div className="text-cyan-200 font-bold text-xs tracking-wide">
                  {getLocalizedSegment(getCustomerSegment(pinnedCustomer), lang).title}
                </div>
                <div className="text-[10px] text-cyan-400/70 mt-0.5">
                  {getLocalizedSegment(getCustomerSegment(pinnedCustomer), lang).incomeTier} • {getLocalizedSegment(getCustomerSegment(pinnedCustomer), lang).loyaltyTier}
                </div>
              </div>

              {/* Detail Stats */}
              <div className="space-y-1.5 text-xs border-t border-cyan-500/30 pt-2.5">
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-cyan-400/70">Số lần ghé thăm:</span>
                  <span className="text-emerald-300 font-bold">
                    {pinnedCustomer?.total_visits || (pinnedCustomer?.customer_type !== "guest" ? 1 : "Lần đầu")}
                  </span>
                </div>
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-cyan-400/70">Tổng chi tiêu:</span>
                  <span className="text-emerald-300 font-bold">
                    {pinnedCustomer?.total_spending
                      ? new Intl.NumberFormat(lang === "vi" ? "vi-VN" : "en-US", {
                          style: "currency",
                          currency: lang === "vi" ? "VND" : "USD",
                        }).format(pinnedCustomer.total_spending)
                      : "0 ₫"}
                  </span>
                </div>
                {pinnedCustomer?.phone && (
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-cyan-400/70">Số điện thoại:</span>
                    <span className="text-cyan-200">{pinnedCustomer.phone}</span>
                  </div>
                )}
                {pinnedCustomer?.note && (
                  <div className="text-[11px] text-cyan-300/80 bg-cyan-950/60 p-2 rounded border border-cyan-500/20 line-clamp-2">
                    <span className="text-cyan-400/80 font-bold">Ghi chú:</span> {pinnedCustomer.note}
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="mt-3 pt-2.5 border-t border-cyan-500/30 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (onCustomerClick) {
                      const target = pinnedCustomer || {
                        id: pinnedFace.id,
                        track_id: pinnedFace.id,
                        name: getCustomerDisplayName(pinnedCustomer, pinnedFace, lang),
                        customer_type: "guest",
                      };
                      onCustomerClick(target);
                    }
                  }}
                  className="flex-1 py-1.5 px-3 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-[11px] tracking-wider uppercase shadow-[0_0_10px_rgba(6,182,212,0.4)] transition cursor-pointer flex items-center justify-center gap-1.5"
                >
                  <span>📝</span> Mở hồ sơ đầy đủ
                </button>
                <button
                  type="button"
                  onClick={() => setPinnedFace(null)}
                  className="py-1.5 px-3 rounded-lg bg-slate-900 hover:bg-slate-800 border border-cyan-500/50 text-cyan-300 font-bold text-[11px] transition cursor-pointer"
                >
                  Tiếp tục xem
                </button>
              </div>
            </div>
          </div>
        )}


        {/* Hidden capture canvas */}
        <canvas ref={canvasRef} className="hidden" />

        {/* Camera error / Video test fallback banner */}
        {cameraError ? (
          <div className="absolute inset-x-4 bottom-4 rounded-2xl border border-amber-200/80 bg-white/95 dark:bg-slate-900/95 p-4 text-sm shadow-xl backdrop-blur-md flex flex-col sm:flex-row items-center justify-between gap-3 z-30">
            <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
              <span className="text-amber-500 font-bold">⚠️ Camera:</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">{cameraError}</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setSelectedDeviceId("sample_video")}
                className="px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs shadow-md transition flex items-center gap-1.5"
              >
                <span>🎬</span> Chạy Video mẫu
              </button>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="px-3.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-medium text-xs transition flex items-center gap-1.5"
              >
                <span>📁</span> Chọn Video từ máy
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
