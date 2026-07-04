"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import { Search, SlidersHorizontal, ChevronDown, Calendar, RefreshCcw, Camera } from "lucide-react";
import { fetchHistory, fetchCameras } from "../../services/api";

const RANK_PILL = {
  VIP: "bg-yellow-50 text-yellow-700 border-yellow-200",
  Member: "bg-blue-50 text-blue-700 border-blue-200",
  Guest: "bg-slate-100 text-slate-600 border-slate-200",
};

export default function HistoryPage() {
  const router = useRouter();
  const [role, setRole] = useState(null);
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  
  // Filters
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [cameraId, setCameraId] = useState("");
  
  // Cameras for filter
  const [cameras, setCameras] = useState([]);

  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    setRole(savedRole);
  }, [router]);

  useEffect(() => {
    if (role) {
      loadCameras();
    }
  }, [role]);

  useEffect(() => {
    if (role) {
      loadHistory();
    }
  }, [role, page, limit, cameraId]);

  async function loadCameras() {
    try {
      const res = await fetchCameras();
      if (res.status === "success") {
        setCameras(res.cameras || []);
      }
    } catch (err) {
      console.error("Failed to load cameras:", err);
    }
  }

  async function loadHistory() {
    setIsLoading(true);
    try {
      const res = await fetchHistory({
        page,
        limit,
        query,
        camera_id: cameraId
      });
      if (res.status === "success") {
        setLogs(res.data || []);
        setTotal(res.total || 0);
      }
    } catch (err) {
      console.error("Failed to load history:", err);
    } finally {
      setIsLoading(false);
    }
  }

  const handleSearch = (e) => {
    if (e.key === 'Enter') {
      setPage(1);
      loadHistory();
    }
  };

  const handleRefresh = () => {
    loadHistory();
  };

  const totalPages = Math.ceil(total / limit);

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="history" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 bg-slate-50">
          <PageHeader
            title="Lịch sử Nhận diện"
            subtitle="Theo dõi toàn bộ lịch sử ra vào và nhận diện từ các camera."
          />

          <div className="flex flex-1 min-h-0 flex-col p-4 sm:p-5 lg:p-6">
            {/* Search + filter bar */}
            <div className="mb-4 flex shrink-0 items-center gap-3">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleSearch}
                  placeholder="Tìm kiếm theo tên hoặc ID..."
                  className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-4 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-blue-400"
                />
              </div>
              
              <div className="ml-auto flex items-center gap-2">
                <select
                  value={cameraId}
                  onChange={(e) => { setCameraId(e.target.value); setPage(1); }}
                  className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-600 outline-none hover:bg-slate-50"
                >
                  <option value="">Tất cả Camera</option>
                  {cameras.map(c => (
                    <option key={c.camera_id} value={c.camera_id}>{c.display_name || c.camera_id}</option>
                  ))}
                </select>

                <button 
                  onClick={handleRefresh}
                  className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-600 hover:bg-slate-50"
                >
                  <RefreshCcw className="h-4 w-4" />
                  Làm mới
                </button>
              </div>
            </div>

            {/* Table */}
            <div className="min-h-0 flex-1 flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white">
              <div className="flex-1 overflow-auto">
                {isLoading ? (
                  <div className="px-5 py-8 text-center text-sm text-slate-400">
                    Đang tải lịch sử...
                  </div>
                ) : logs.length === 0 ? (
                  <div className="px-5 py-8 text-center text-sm text-slate-400">
                    Không tìm thấy dữ liệu.
                  </div>
                ) : (
                  <table className="w-full min-w-[700px] table-auto text-left">
                    <thead className="sticky top-0 bg-white shadow-sm z-10">
                      <tr className="border-b border-slate-100">
                        {["Thời gian", "Camera", "Khách hàng", "Mã ID", "Phân loại"].map((col) => (
                          <th key={col} className="px-5 py-3.5 text-xs font-medium text-slate-400 uppercase tracking-wider">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {logs.map((log) => {
                        const date = new Date(log.timestamp);
                        const timeStr = date.toLocaleTimeString("vi-VN");
                        const dateStr = date.toLocaleDateString("vi-VN");
                        const displayId = log.customer_id && log.customer_id.startsWith("GUEST_") ? log.customer_id : `CLIENT_${log.customer_id}`;
                        const rank = log.loyalty_tier === "VIP" ? "VIP" : log.customer_type === "registered" ? "Member" : "Guest";
                        
                        return (
                          <tr key={log.id} className="hover:bg-slate-50/60 transition-colors">
                            <td className="px-5 py-3">
                              <div className="flex flex-col">
                                <span className="text-sm font-medium text-slate-900">{timeStr}</span>
                                <span className="text-xs text-slate-500">{dateStr}</span>
                              </div>
                            </td>
                            <td className="px-5 py-3">
                              <div className="flex items-center gap-2">
                                <Camera className="h-4 w-4 text-slate-400" />
                                <span className="text-sm text-slate-700">{log.camera_name || log.camera_id}</span>
                              </div>
                            </td>
                            <td className="px-5 py-3">
                              <div className="flex items-center gap-3">
                                <div className="h-8 w-8 shrink-0 rounded-full bg-gradient-to-br from-blue-100 to-slate-200" />
                                <Link
                                  href={`/customers/${log.customer_id}`}
                                  className="text-sm font-semibold text-slate-900 hover:text-blue-600"
                                >
                                  {log.customer_name || "Khách chưa đăng ký"}
                                </Link>
                              </div>
                            </td>
                            <td className="px-5 py-3 text-sm text-slate-500 font-mono">
                              {displayId}
                            </td>
                            <td className="px-5 py-3">
                              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${RANK_PILL[rank] || RANK_PILL.Guest}`}>
                                {rank}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
              
              {/* Pagination */}
              {!isLoading && total > 0 && (
                <div className="flex shrink-0 items-center justify-between border-t border-slate-200 bg-slate-50 px-5 py-3">
                  <div className="text-sm text-slate-500">
                    Hiển thị <span className="font-medium text-slate-900">{(page - 1) * limit + 1}</span> đến <span className="font-medium text-slate-900">{Math.min(page * limit, total)}</span> trong <span className="font-medium text-slate-900">{total}</span> kết quả
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                    >
                      Trang trước
                    </button>
                    <div className="text-sm font-medium text-slate-700 px-2">
                      {page} / {totalPages}
                    </div>
                    <button
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                    >
                      Trang sau
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
