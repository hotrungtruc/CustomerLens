"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import CameraStream from "../../components/CameraStream";
import { Maximize2, RefreshCw, X } from "lucide-react";

const CAMERA_NAMES = [
  "Cổng chính",
  "Hành lang A",
  "Sảnh tiếp tân",
  "Bãi giữ xe",
  "Khu quầy 1",
  "Khu quầy 2",
  "Cửa phụ",
  "Kho hàng",
  "Cầu thang",
  "Sảnh chờ",
  "Lối VIP",
  "Khu giao nhận",
  "Phòng họp",
  "Tầng 2",
  "Tầng 3",
  "Back office",
  "Khu kỹ thuật",
  "Cổng sau",
];

const OFFLINE_CAMERA_INDEXES = new Set([4, 9, 14, 17]);

const CAMERAS = CAMERA_NAMES.map((name, index) => ({
  id: `DSLR-${String(index + 1).padStart(3, "0")}`,
  name,
  status: OFFLINE_CAMERA_INDEXES.has(index) ? "offline" : "live",
  detections: (index % 4) + 1,
}));

function CameraBadge({ cam }) {
  return (
    <div className="min-w-0 text-white">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-xs font-semibold sm:text-sm">
          {cam.name}
        </span>
        <span className="shrink-0 text-[10px] text-white/65">({cam.id})</span>
      </div>
      {cam.status === "live" ? (
        <span className="mt-0.5 inline-flex items-center gap-1 text-[10px] font-semibold text-red-200">
          <span className="h-1.5 w-1.5 rounded-full bg-red-400 animate-pulse" />
          LIVE
        </span>
      ) : (
        <span className="mt-0.5 inline-flex text-[10px] font-semibold text-slate-200">
          Offline
        </span>
      )}
    </div>
  );
}

function CameraTile({ cam, onExpand }) {
  return (
    <div className="group relative h-full min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-950 shadow-sm">
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-2 bg-gradient-to-b from-slate-950/85 via-slate-950/45 to-transparent p-2">
        <CameraBadge cam={cam} />
        <button
          type="button"
          onClick={onExpand}
          className="pointer-events-auto rounded-md border border-white/20 bg-white/15 p-1 text-white/80 backdrop-blur hover:bg-white/25 hover:text-white"
          aria-label={`Phóng to ${cam.name}`}
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {cam.status === "offline" ? (
        <div className="relative h-full overflow-hidden bg-slate-900">
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/60 pt-8">
            <span className="text-xs font-medium text-white/80">
              Mất kết nối
            </span>
          </div>
        </div>
      ) : (
        <CameraStream sessionId={cam.id} framed={false} compact />
      )}
    </div>
  );
}

function ExpandedCameraModal({ cam, onClose }) {
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm sm:p-6 lg:p-8"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="relative flex max-h-[82dvh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-white shadow-2xl">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-800">
              {cam.name}
            </span>
            <span className="text-xs text-slate-400">({cam.id})</span>
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-600">
              Expanded
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-md border border-slate-200 bg-white p-1.5 text-slate-500 hover:bg-slate-50 hover:text-slate-900"
            aria-label="Đóng phóng to"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {cam.status === "offline" ? (
          <div className="flex h-[calc(82dvh-49px)] min-h-[320px] items-center justify-center bg-slate-900">
            <span className="text-base font-medium text-white">
              Mất kết nối
            </span>
          </div>
        ) : (
          <div className="h-[calc(82dvh-49px)] min-h-[320px] bg-slate-950">
            <CameraStream sessionId={cam.id} framed={false} compact />
          </div>
        )}
      </div>
    </div>
  );
}

export default function CameraPage() {
  const router = useRouter();
  const [filter, setFilter] = useState("all");
  const [role, setRole] = useState(null);
  const [allowedCameras, setAllowedCameras] = useState([]);
  const [expandedCameraId, setExpandedCameraId] = useState(null);

  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    if (savedRole === "guest") {
      router.push("/login");
      return;
    }
    setRole(savedRole);
    try {
      const cams = JSON.parse(localStorage.getItem("cameras")) || [];
      setAllowedCameras(cams);
    } catch {
      setAllowedCameras([]);
    }
  }, [router]);

  const counts = useMemo(() => {
    const live = CAMERAS.filter((cam) => cam.status === "live").length;
    return {
      all: CAMERAS.length,
      live,
      offline: CAMERAS.length - live,
    };
  }, []);

  const filters = useMemo(
    () => [
      { key: "all", label: "Tất cả", count: counts.all },
      { key: "live", label: "Đang live", count: counts.live },
      { key: "offline", label: "Offline", count: counts.offline },
    ],
    [counts],
  );

  if (role === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="font-medium text-slate-500">Đang tải...</p>
      </div>
    );
  }

  const filteredCameras =
    role === "admin"
      ? CAMERAS
      : CAMERAS.filter((cam) => allowedCameras.includes(cam.id));

  const shown =
    filter === "all"
      ? filteredCameras
      : filteredCameras.filter((cam) => cam.status === filter);

  const expandedCamera =
    shown.find((cam) => cam.id === expandedCameraId) || null;

  return (
    <main className="h-dvh overflow-hidden bg-slate-50 p-2 sm:p-3 lg:p-4">
      <div className="mx-auto flex h-full max-w-[1400px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="camera" />

        <div className="flex min-w-0 min-h-0 flex-col">
          <PageHeader
            title="Quản lý Camera"
            subtitle="Theo dõi tất cả camera trực tiếp trong hệ thống."
          />

          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2 sm:px-4">
            <div className="flex flex-wrap items-center gap-2">
              {filters.map((item) => (
                <button
                  key={item.key}
                  onClick={() => setFilter(item.key)}
                  className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition sm:text-sm ${
                    filter === item.key
                      ? "bg-blue-600 text-white"
                      : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {item.label} ({item.count})
                </button>
              ))}
            </div>

            <button className="rounded-md border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50">
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>

          <div className="grid flex-1 min-h-0 auto-rows-fr grid-cols-1 gap-2 overflow-hidden p-2 sm:grid-cols-2 lg:grid-cols-6">
            {shown.map((cam) => {
              if (expandedCameraId === cam.id) return null;

              return (
                <CameraTile
                  key={cam.id}
                  cam={cam}
                  onExpand={() => setExpandedCameraId(cam.id)}
                />
              );
            })}
          </div>
        </div>
      </div>

      {expandedCamera ? (
        <ExpandedCameraModal
          cam={expandedCamera}
          onClose={() => setExpandedCameraId(null)}
        />
      ) : null}
    </main>
  );
}
