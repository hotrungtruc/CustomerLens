"use client";

import { useServerStatus } from "../hooks/useServerStatus";
import { useEffect, useState } from "react";

export default function ServerGate({ children }) {
  const { status, wakeServer, error } = useServerStatus();
  const [countdown, setCountdown] = useState(90);

  // Countdown timer for waking state
  useEffect(() => {
    let interval;
    if (status === "waking") {
      setCountdown(90);
      interval = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(interval);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } else {
      setCountdown(90);
    }
    return () => clearInterval(interval);
  }, [status]);

  const progressPercent = Math.min(100, Math.max(0, ((90 - countdown) / 90) * 100));

  if (status === "checking") {
    return (
      <div className="flex h-screen w-screen flex-col items-center justify-center bg-slate-900 font-sans text-white">
        <div className="relative flex h-16 w-16 items-center justify-center">
          <div className="absolute h-12 w-12 animate-ping rounded-full bg-blue-500/20"></div>
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
        </div>
        <p className="mt-4 text-sm font-medium text-slate-400 animate-pulse">
          Đang kiểm tra kết nối với máy chủ AI...
        </p>
      </div>
    );
  }

  if (status === "offline") {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-slate-950 font-sans text-white p-4">
        {/* Decorative background glow */}
        <div className="absolute top-1/4 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-blue-500/10 blur-[100px] pointer-events-none"></div>
        <div className="absolute bottom-1/4 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-indigo-500/5 blur-[120px] pointer-events-none"></div>

        <div className="relative z-10 w-full max-w-md overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/60 p-8 shadow-2xl backdrop-blur-xl text-center">
          {/* Sleep / Moon Icon Container */}
          <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-full bg-slate-800/80 border border-slate-700/50 relative shadow-inner">
            {/* Pulsing ring */}
            <div className="absolute inset-0 rounded-full border border-blue-500/30 animate-pulse"></div>
            
            <svg
              className="h-10 w-10 text-blue-400 filter drop-shadow-[0_0_8px_rgba(96,165,250,0.5)]"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth="1.5"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"
              />
            </svg>
            
            {/* Small floating sleep letters (Zzz) */}
            <span className="absolute top-4 right-4 text-xs font-bold text-blue-400/80 animate-bounce delay-100">z</span>
            <span className="absolute top-2 right-8 text-[10px] font-bold text-blue-400/60 animate-bounce delay-300">z</span>
            <span className="absolute top-6 right-2 text-[14px] font-bold text-blue-400 animate-bounce">Z</span>
          </div>

          <h1 className="mt-6 text-2xl font-bold tracking-tight text-white font-display">
            Hệ thống đang tạm nghỉ
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-400">
            Để tiết kiệm chi phí hạ tầng đám mây AWS, máy chủ xử lý AI (Face Recognition) hiện đang ở trạng thái ngủ.
          </p>

          <div className="mt-8">
            <button
              onClick={wakeServer}
              className="group relative flex w-full items-center justify-center gap-2 rounded-2xl bg-blue-600 px-6 py-4 text-sm font-semibold text-white shadow-lg transition-all duration-200 hover:bg-blue-500 hover:shadow-blue-500/25 active:scale-[0.98]"
            >
              <svg
                className="h-5 w-5 transition-transform group-hover:scale-110"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth="2"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"
                />
              </svg>
              Đánh thức Hệ thống
            </button>
          </div>

          {error && (
            <div className="mt-4 rounded-xl bg-red-950/50 border border-red-900/50 p-3 text-left">
              <p className="text-xs text-red-400">
                <span className="font-semibold">Lỗi:</span> {error}
              </p>
            </div>
          )}

          <div className="mt-6 text-[10px] text-slate-500">
            Lịch hoạt động tự động: 8h00 - 22h00 hàng ngày.
          </div>
        </div>
      </div>
    );
  }

  if (status === "waking") {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-slate-950 font-sans text-white p-4">
        {/* Glow */}
        <div className="absolute top-1/4 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-blue-500/10 blur-[100px] pointer-events-none"></div>

        <div className="relative z-10 w-full max-w-md overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/60 p-8 shadow-2xl backdrop-blur-xl text-center">
          {/* Loading Animation Ring */}
          <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-full bg-slate-800/80 border border-slate-700/50 relative">
            {/* Spinning gradient */}
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-blue-500 border-r-blue-500 animate-spin"></div>
            
            <svg
              className="h-10 w-10 text-blue-400 animate-pulse"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth="1.5"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z"
              />
            </svg>
          </div>

          <h1 className="mt-6 text-xl font-bold tracking-tight text-white font-display">
            Đang kích hoạt máy chủ...
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-400 px-2">
            Hệ thống đang khởi động máy ảo AWS EC2, cập nhật IP Cloudflare và tải các mô hình học máy.
          </p>

          {/* Countdown & Progress bar */}
          <div className="mt-8 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400 px-1">
              <span>Tiến trình</span>
              <span className="font-semibold text-blue-400">còn {countdown} giây...</span>
            </div>
            
            {/* Progress Track */}
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-blue-600 to-indigo-500 shadow-[0_0_8px_rgba(59,130,246,0.5)] transition-all duration-1000 ease-linear"
                style={{ width: `${progressPercent}%` }}
              ></div>
            </div>
          </div>

          <p className="mt-4 text-[11px] text-slate-500 animate-pulse">
            Vui lòng không đóng trình duyệt lúc này. Giao diện sẽ tự động tải lại khi sẵn sàng.
          </p>
        </div>
      </div>
    );
  }

  // status === 'online'
  return children;
}
