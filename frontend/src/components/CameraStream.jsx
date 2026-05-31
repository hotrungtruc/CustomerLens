"use client";

import { useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "../services/api";

const CAPTURE_INTERVAL_MS = 900;
const JPEG_QUALITY = 0.75;

export default function CameraStream() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const sendingRef = useRef(false);
  const [status, setStatus] = useState("Requesting camera access...");
  const [error, setError] = useState("");

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
        const width = video.videoWidth || 640;
        const height = video.videoHeight || 360;
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

        if (!cancelled) {
          setStatus("Camera live");
          setError("");
        }
      } catch (fetchError) {
        if (!cancelled) {
          setStatus("Camera live, waiting for backend");
          setError("Unable to send frames to backend");
        }
      } finally {
        sendingRef.current = false;
      }
    };

    const startCamera = async () => {
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
          video: {
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
    };
  }, []);

  return (
    <div className="mt-6 overflow-hidden rounded-2xl border border-black/5 bg-ink/95">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 text-sm text-sand/80">
        <span>{status}</span>
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
