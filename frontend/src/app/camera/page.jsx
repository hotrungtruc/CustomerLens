"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import CameraViewer from "../../components/CameraViewer";
import { Maximize2, RefreshCw, X, Wifi, WifiOff } from "lucide-react";
import { fetchActiveSessions } from "../../services/api";

/* ── Session badge (top-left overlay) ───────────────────────────────────── */
function SessionBadge({ session }) {
  const isActive = session.active;
  return (
    <div className="min-w-0 text-white">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-xs font-semibold sm:text-sm">
          {session.session_id}
        </span>
      </div>
      {isActive ? (
        <span className="mt-0.5 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-300">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          LIVE
        </span>
      ) : (
        <span className="mt-0.5 inline-flex items-center gap-1 text-[10px] font-semibold text-slate-300">
          <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
          Idle
        </span>
      )}
    </div>
  );
}

/* ── Camera tile ────────────────────────────────────────────────────────── */
function CameraTile({ session, onExpand }) {
  return (
    <div className="group relative h-full min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-950 shadow-sm">
      {/* Top overlay */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-2 bg-gradient-to-b from-slate-950/85 via-slate-950/45 to-transparent p-2">
        <SessionBadge session={session} />
        <button
          type="button"
          onClick={onExpand}
          className="pointer-events-auto rounded-md border border-white/20 bg-white/15 p-1 text-white/80 backdrop-blur hover:bg-white/25 hover:text-white"
          aria-label={`Phóng to ${session.session_id}`}
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Face count badge */}
      {session.face_count > 0 && (
        <div className="absolute bottom-2 right-2 z-10 flex items-center gap-1 rounded-full bg-blue-600/90 px-2 py-0.5 text-[10px] font-semibold text-white shadow backdrop-blur">
          {session.face_count} khuôn mặt
        </div>
      )}

      {session.active ? (
        <CameraViewer sessionId={session.session_id} compact refreshInterval={800} />
      ) : (
        <div className="relative h-full overflow-hidden bg-slate-900">
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-slate-900/60">
            <WifiOff className="h-5 w-5 text-white/40" />
            <span className="text-xs font-medium text-white/50">
              Không có tín hiệu
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Expanded modal ─────────────────────────────────────────────────────── */
function ExpandedModal({ session, onClose }) {
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm sm:p-6 lg:p-8"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative flex max-h-[82dvh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-white shadow-2xl">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-800">
              {session.session_id}
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.2em] ${
                session.active
                  ? "bg-emerald-50 text-emerald-600"
                  : "bg-slate-100 text-slate-500"
              }`}
            >
              {session.active ? "Live" : "Idle"}
            </span>
            {session.face_count > 0 && (
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-600">
                {session.face_count} khuôn mặt
              </span>
            )}
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

        <div className="h-[calc(82dvh-49px)] min-h-[320px] bg-slate-950">
          {session.active ? (
            <CameraViewer sessionId={session.session_id} refreshInterval={300} />
          ) : (
            <div className="flex h-full items-center justify-center">
              <span className="text-base font-medium text-white/60">
                Không có tín hiệu
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Empty state ────────────────────────────────────────────────────────── */
function EmptyState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100">
        <Wifi className="h-7 w-7 text-slate-400" />
      </div>
      <div className="text-center">
        <p className="text-sm font-semibold text-slate-700">
          Chưa có thiết bị nào kết nối
        </p>
        <p className="mt-1 text-xs text-slate-400">
          Khi khách truy cập trang chủ và bật camera, thiết bị sẽ tự động xuất
          hiện ở đây.
        </p>
      </div>
    </div>
  );
}

/* ── Main page ──────────────────────────────────────────────────────────── */
export default function CameraPage() {
  const router = useRouter();
  const [filter, setFilter] = useState("all");
  const [role, setRole] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // Auth check
  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    if (savedRole === "guest") {
      router.push("/login");
      return;
    }
    setRole(savedRole);
  }, [router]);

  // Poll active sessions
  const loadSessions = useCallback(async () => {
    try {
      const data = await fetchActiveSessions();
      if (data.status === "success") {
        setSessions(data.sessions || []);
      }
    } catch (_) {}
    setIsLoading(false);
  }, []);

  useEffect(() => {
    if (!role) return;
    loadSessions();
    const interval = setInterval(loadSessions, 3000);
    return () => clearInterval(interval);
  }, [role, loadSessions]);

  // Counts
  const counts = useMemo(() => {
    const active = sessions.filter((s) => s.active).length;
    return { all: sessions.length, active, idle: sessions.length - active };
  }, [sessions]);

  const filters = useMemo(
    () => [
      { key: "all", label: "Tất cả", count: counts.all },
      { key: "active", label: "Đang live", count: counts.active },
      { key: "idle", label: "Idle", count: counts.idle },
    ],
    [counts],
  );

  // Loading state
  if (role === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="font-medium text-slate-500">Đang tải...</p>
      </div>
    );
  }

  // Filter
  const shown =
    filter === "all"
      ? sessions
      : filter === "active"
        ? sessions.filter((s) => s.active)
        : sessions.filter((s) => !s.active);

  const expandedSession =
    shown.find((s) => s.session_id === expandedId) || null;

  // Dynamic grid columns based on session count
  const gridCols =
    shown.length <= 1
      ? "grid-cols-1"
      : shown.length <= 4
        ? "grid-cols-1 sm:grid-cols-2"
        : shown.length <= 9
          ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
          : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="camera" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 bg-slate-50">
          <PageHeader
            title="Quản lý Camera"
            subtitle="Theo dõi tất cả thiết bị đang kết nối vào hệ thống."
          />

          {/* Filter bar */}
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

            <button
              onClick={loadSessions}
              className="rounded-md border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50"
              title="Làm mới"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>

          {/* Grid or empty state */}
          {isLoading ? (
            <div className="flex flex-1 items-center justify-center">
              <p className="text-sm text-slate-400">
                Đang tải danh sách thiết bị…
              </p>
            </div>
          ) : shown.length === 0 ? (
            <EmptyState />
          ) : (
            <div
              className={`grid flex-1 min-h-0 auto-rows-fr gap-2 overflow-auto p-2 ${gridCols}`}
            >
              {shown.map((session) => (
                <CameraTile
                  key={session.session_id}
                  session={session}
                  onExpand={() => setExpandedId(session.session_id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {expandedSession ? (
        <ExpandedModal
          session={expandedSession}
          onClose={() => setExpandedId(null)}
        />
      ) : null}
    </main>
  );
}
