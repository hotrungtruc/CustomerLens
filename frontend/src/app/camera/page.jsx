"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import CameraStream from "../../components/CameraStream";
import { useCustomerDetection } from "../../hooks/useCustomerDetection";
import { Maximize2, RefreshCw } from "lucide-react";

const CAMERAS = [
  { id: "DSLR-001", name: "Cổng chính",    status: "live",    detections: 3 },
  { id: "DSLR-002", name: "Hành lang A",   status: "live",    detections: 1 },
  { id: "DSLR-003", name: "Sảnh tiếp tân", status: "live",    detections: 2 },
  { id: "DSLR-004", name: "Bãi giữ xe",    status: "offline", detections: 0 },
];

const FILTERS = [
  { key: "all",     label: "Tất cả",     count: 4 },
  { key: "live",    label: "Đang live",  count: 3 },
  { key: "offline", label: "Offline",    count: 1 },
];

export default function CameraPage() {
  const router = useRouter();
  const [filter, setFilter] = useState("all");
  const [role, setRole] = useState(null);
  const [allowedCameras, setAllowedCameras] = useState([]);
  const { status, customers, frameSize } = useCustomerDetection();

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

  if (role === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-slate-500 font-medium">Đang tải...</p>
      </div>
    );
  }

  const filteredCameras = role === "admin"
    ? CAMERAS
    : CAMERAS.filter((c) => allowedCameras.includes(c.id));

  const shown = filter === "all"
    ? filteredCameras
    : filteredCameras.filter((c) => c.status === filter);


  return (
    <main className="min-h-screen bg-slate-50 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-[1400px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid lg:grid-cols-[220px_minmax(0,1fr)]">
        <Sidebar active="camera" />

        <div className="flex min-w-0 flex-col">
          <PageHeader
            title="Quản lý Camera"
            subtitle="Theo dõi tất cả camera trực tiếp trong hệ thống."
          />

          {/* Toolbar */}
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-3">
            <div className="flex items-center gap-2">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    filter === f.key
                      ? "bg-blue-600 text-white"
                      : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {f.label} ({f.count})
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <select className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 outline-none">
                <option>Lưới 2×2</option>
                <option>Lưới 1×1</option>
              </select>
              <button className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50">
                <RefreshCw className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Grid */}
          <div className="grid flex-1 gap-5 overflow-auto p-6 md:grid-cols-2">
            {shown.map((cam, i) => (
              <div
                key={cam.id}
                className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
              >
                {/* Card header */}
                <div className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-800">{cam.name}</span>
                    <span className="text-xs text-slate-400">({cam.id})</span>
                    {cam.status === "live" ? (
                      <span className="flex items-center gap-1 text-xs font-semibold text-red-500">
                        <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
                        LIVE
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">Offline</span>
                    )}
                  </div>
                  <button className="rounded-lg border border-slate-200 p-1 text-slate-400 hover:bg-slate-50">
                    <Maximize2 className="h-3.5 w-3.5" />
                  </button>
                </div>

                {/* Feed */}
                {i === 0 ? (
                  <CameraStream
                    customers={status === "success" ? customers : []}
                    frameSize={frameSize}
                  />
                ) : cam.status === "offline" ? (
                  <div className="relative aspect-[16/10] overflow-hidden bg-slate-800">
                    <div className="absolute inset-0 flex items-center justify-center bg-slate-900/60">
                      <span className="text-sm font-medium text-white">Mất kết nối</span>
                    </div>
                  </div>
                ) : (
                  <div className="relative aspect-[16/10] overflow-hidden bg-slate-100">
                    <div
                      className="h-full w-full bg-cover bg-center"
                      style={{ backgroundImage: `url(https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&q=60)` }}
                    />
                    {cam.detections > 0 && (
                      <span className="absolute right-3 top-3 rounded-full bg-blue-600 px-2.5 py-1 text-xs font-semibold text-white">
                        {cam.detections} phát hiện
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
