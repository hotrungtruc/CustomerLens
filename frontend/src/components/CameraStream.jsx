"use client";

import { useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "../services/api";

const CAPTURE_INTERVAL_MS = 350;
const JPEG_QUALITY = 0.75;
const MAX_UPLOAD_WIDTH = 640;
const MAX_UPLOAD_HEIGHT = 360;

const TRACK_BADGE_THEMES = [
  { base: "bg-sky-500", ring: "ring-sky-300/80" },
  { base: "bg-fuchsia-500", ring: "ring-fuchsia-300/80" },
  { base: "bg-amber-500", ring: "ring-amber-300/80" },
  { base: "bg-emerald-500", ring: "ring-emerald-300/80" },
  { base: "bg-indigo-500", ring: "ring-indigo-300/80" },
  { base: "bg-rose-500", ring: "ring-rose-300/80" },
];

function getTrackBadge(trackId) {
  const safeTrack = Number(trackId || 0);
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const symbol = safeTrack > 0
    ? alphabet[(safeTrack - 1) % alphabet.length]
    : "?";
  return {
    symbol,
    theme: TRACK_BADGE_THEMES[safeTrack % TRACK_BADGE_THEMES.length],
  };
}

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
    <div className="mt-6 overflow-hidden rounded-2xl border border-black/5 bg-ink/95">
      <div className="flex flex-col gap-3 border-b border-white/10 px-4 py-3 text-sm text-sand/80 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:gap-3">
          <span>{status}</span>
          <select
            value={selectedDeviceId}
            onChange={handleCameraChange}
            className="min-w-[240px] rounded-xl border border-white/10 bg-sand px-3 py-2 text-sm text-ink outline-none transition focus:border-copper"
          >
            <option value="">Default camera</option>
            {devices.map((device, index) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label || `Camera ${index + 1}`}
              </option>
            ))}
          </select>
        </div>
        <span className="rounded-full bg-white/10 px-3 py-1 text-[11px] uppercase tracking-[0.25em] text-sand/70">
          Browser cam
        </span>
      </div>

      <div className="relative bg-black">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="h-[420px] w-full object-cover"
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
                  className={`absolute rounded-xl border-2 transition-all duration-300 ease-out ${
                    isHighlighted
                      ? "border-white shadow-[0_0_0_4px_rgba(255,255,255,0.45)]"
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
                    className={`-mt-8 ml-0 inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold text-white ring-2 ${theme.base} ${theme.ring} ${
                      isHighlighted ? "scale-110" : ""
                    }`}
                  >
                    {symbol}
                  </div>
                </div>
              );
            })}
        </div>

        <canvas ref={canvasRef} className="hidden" />

        {error ? (
          <div className="absolute inset-x-4 bottom-4 rounded-2xl bg-sand/95 px-4 py-3 text-sm text-ink shadow-glow">
            {error}
          </div>
        ) : null}
      </div>
    </div>
  );
}
