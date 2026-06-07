"use client";

import { useEffect, useRef, useState } from "react";
import { Camera } from "lucide-react";

import { API_BASE_URL } from "../services/api";
import { getTrackBadge } from "./trackBadge";

const CAPTURE_INTERVAL_MS = 350;
const JPEG_QUALITY = 0.75;
const MAX_UPLOAD_WIDTH = 640;
const MAX_UPLOAD_HEIGHT = 360;

export default function CameraStream({
  customers = [],
  frameSize = { width: 640, height: 360 },
  highlightedTrackId = null,
}) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const sendingRef = useRef(false);
  const mountedRef = useRef(true);
  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [status, setStatus] = useState("Requesting camera access...");
  const [error, setError] = useState("");

  const sendFrame = async () => {
    if (sendingRef.current) {
      return;
    }

    const video = videoRef.current;
    const canvas = canvasRef.current;

    if (!video || !canvas || video.readyState < 2) {
      return;
    }

    const context = canvas.getContext("2d", { willReadFrequently: false });
    if (!context) {
      return;
    }

    sendingRef.current = true;

    try {
      const sourceWidth = video.videoWidth || 640;
      const sourceHeight = video.videoHeight || 360;
      const scale = Math.min(
        1,
        MAX_UPLOAD_WIDTH / sourceWidth,
        MAX_UPLOAD_HEIGHT / sourceHeight
      );
      const width = Math.max(1, Math.round(sourceWidth * scale));
      const height = Math.max(1, Math.round(sourceHeight * scale));

      canvas.width = width;
      canvas.height = height;
      context.drawImage(video, 0, 0, width, height);

      const image = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
      await fetch(`${API_BASE_URL}/api/process_frame`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ image }),
      });

      if (mountedRef.current) {
        setStatus("Camera live");
        setError("");
      }
    } catch (fetchError) {
      if (mountedRef.current) {
        setStatus("Camera live, waiting for backend");
        setError("Unable to send frames to backend");
      }
    } finally {
      sendingRef.current = false;
    }
  };

  useEffect(() => {
    let cancelled = false;

    const stopStream = () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    };

    const loadDevices = async () => {
      const mediaDevices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = mediaDevices.filter((device) => device.kind === "videoinput");
      if (cancelled) {
        return [];
      }

      setDevices(videoDevices);
      return videoDevices;
    };

    const startCamera = async (deviceId = "") => {
      stopStream();

      try {
        if (
          !window.isSecureContext &&
          window.location.hostname !== "localhost" &&
          window.location.hostname !== "127.0.0.1"
        ) {
          throw new Error("Camera requires HTTPS or localhost.");
        }

        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("This browser does not support camera access.");
        }

        const stream = await navigator.mediaDevices.getUserMedia({
          video: deviceId
            ? {
              deviceId: { exact: deviceId },
            }
            : {
              facingMode: "user",
            },
          audio: false,
        });

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        streamRef.current = stream;

        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play();
        }

        const discoveredDevices = await loadDevices();
        if (!deviceId && discoveredDevices.length > 0 && !selectedDeviceId) {
          setSelectedDeviceId(discoveredDevices[0].deviceId);
        }

        setStatus("Camera live");
        setError("");
        timerRef.current = window.setInterval(sendFrame, CAPTURE_INTERVAL_MS);
      } catch (cameraError) {
        if (!cancelled) {
          setStatus("Camera unavailable");
          setError(
            cameraError instanceof Error
              ? cameraError.message
              : "Unable to access camera"
          );
        }
      }
    };

    startCamera();

    return () => {
      cancelled = true;
      stopStream();
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedDeviceId) {
      return;
    }

    let cancelled = false;

    const restartCamera = async () => {
      try {
        if (cancelled) {
          return;
        }

        setStatus("Switching camera...");
        setError("");

        const mediaDevices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = mediaDevices.filter((device) => device.kind === "videoinput");
        if (!cancelled) {
          setDevices(videoDevices);
        }

        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            deviceId: { exact: selectedDeviceId },
          },
          audio: false,
        });

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
        }

        if (timerRef.current) {
          window.clearInterval(timerRef.current);
          timerRef.current = null;
        }

        streamRef.current = stream;

        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play();
        }

        setStatus("Camera live");
        timerRef.current = window.setInterval(sendFrame, CAPTURE_INTERVAL_MS);
      } catch (cameraError) {
        if (!cancelled) {
          setStatus("Camera unavailable");
          setError(
            cameraError instanceof Error
              ? cameraError.message
              : "Unable to access camera"
          );
        }
      }
    };

    restartCamera();

    return () => {
      cancelled = true;
    };
  }, [selectedDeviceId]);

  const handleCameraChange = (event) => {
    setSelectedDeviceId(event.target.value);
  };

  return (
    <div className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
      <div className="flex flex-col gap-3 border-b border-slate-200/80 px-4 py-4 text-sm text-slate-500 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-slate-600">{status}</span>
          <select
            value={selectedDeviceId}
            onChange={handleCameraChange}
            className="min-w-[240px] rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none transition focus:border-indigo-300"
          >
            <option value="">Integrated Camera</option>
            {devices.map((device, index) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label || `Camera ${index + 1}`}
              </option>
            ))}
          </select>
        </div>
        <span className="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.25em] text-emerald-600">
          Live feed
        </span>
      </div>

      <div className="relative bg-slate-950">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="aspect-[16/10] h-auto min-h-[220px] w-full object-cover sm:min-h-[340px] md:min-h-[420px]"
        />

        <div className="pointer-events-none absolute inset-0">
          {customers
            .filter((customer) => Array.isArray(customer.bbox) && customer.bbox.length === 4)
            .map((customer) => {
              const [x1, y1, x2, y2] = customer.bbox;
              const left = (x1 / frameSize.width) * 100;
              const top = (y1 / frameSize.height) * 100;
              const width = ((x2 - x1) / frameSize.width) * 100;
              const height = ((y2 - y1) / frameSize.height) * 100;
              const isHighlighted = highlightedTrackId === customer.track_id;
              const { symbol, theme } = getTrackBadge(customer.track_id);

              return (
                <div
                  key={`overlay-${customer.tile_id}`}
                  className={`absolute rounded-2xl border-2 bg-white/5 backdrop-blur-[1px] ${isHighlighted
                      ? "border-white shadow-[0_0_0_4px_rgba(255,255,255,0.35)]"
                      : "border-white/80"
                    }`}
                  style={{
                    left: `${left}%`,
                    top: `${top}%`,
                    width: `${Math.max(width, 6)}%`,
                    height: `${Math.max(height, 8)}%`,
                  }}
                >
                  <div
                    className={`-mt-3 ml-2 inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white ring-2 ring-white/40 ${theme.base} ${theme.ring} ${isHighlighted ? "scale-110" : ""
                      }`}
                  >
                    {symbol}
                  </div>
                </div>
              );
            })}
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center p-4">
          <div className="pointer-events-auto flex items-center gap-2 rounded-[20px] border border-white/10 bg-slate-900/80 px-4 py-3 text-white shadow-[0_16px_40px_rgba(15,23,42,0.35)] backdrop-blur-md">
            <ToolbarIcon label="Snap" active>
              <Camera className="h-4.5 w-4.5" />
            </ToolbarIcon>
            <ToolbarIcon label="Record">
              <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="5" y="7" width="10" height="10" rx="2" />
                <path d="M15 10l4-2v8l-4-2z" />
              </svg>
            </ToolbarIcon>
            <ToolbarIcon label="Mic">
              <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 14a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v4a3 3 0 0 0 3 3Z" />
                <path d="M19 11a7 7 0 0 1-14 0" />
                <path d="M12 18v3" />
              </svg>
            </ToolbarIcon>
            <ToolbarIcon label="Volume">
              <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M11 5 6 9H2v6h4l5 4V5Z" />
                <path d="M15 9a4 4 0 0 1 0 6" />
                <path d="M17.5 6.5a7 7 0 0 1 0 11" />
              </svg>
            </ToolbarIcon>
            <ToolbarIcon label="More">...</ToolbarIcon>
          </div>
        </div>

        <canvas ref={canvasRef} className="hidden" />

        {error ? (
          <div className="absolute inset-x-4 bottom-4 rounded-2xl border border-rose-200 bg-rose-50/95 px-4 py-3 text-sm text-rose-600 shadow-lg">
            {error}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ToolbarIcon({ children, label, active = false }) {
  return (
    <button
      type="button"
      className={`inline-flex h-10 w-10 items-center justify-center rounded-xl transition ${active ? "bg-white text-slate-900 shadow-sm" : "bg-white/10 text-white/85 hover:bg-white/15"
        }`}
      title={label}
    >
      {children}
    </button>
  );
}