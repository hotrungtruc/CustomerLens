"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import MessageBanner from "../../components/MessageBanner";
import { getRecognizeLogs, exportRecognizeLogsCsv, fetchCameras } from "../../services/api";

export default function HistoryPage() {
  const [logs, setLogs] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [banner, setBanner] = useState({ type: null, text: "" });

  // Filter States
  const [search, setSearch] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [cameraId, setCameraId] = useState("all");
  const [customerType, setCustomerType] = useState("all");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [autoRefresh, setAutoRefresh] = useState(false);

  // Aux Data
  const [cameras, setCameras] = useState([]);
  const [selectedLog, setSelectedLog] = useState(null);

  // Load Cameras List for Filter
  useEffect(() => {
    fetchCameras()
      .then((data) => setCameras(data.cameras || []))
      .catch(() => {});
  }, []);

  // Fetch Logs Data
  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getRecognizeLogs({
        search,
        startDate: startDate ? `${startDate} 00:00:00` : "",
        endDate: endDate ? `${endDate} 23:59:59` : "",
        cameraId,
        customerType,
        page,
        limit,
      });

      if (data.success) {
        setLogs(data.logs || []);
        setTotalCount(data.total_count || 0);
        setTotalPages(data.total_pages || 1);
      } else {
        setBanner({ type: "error", text: data.message || "Không thể nạp nhật ký" });
      }
    } catch (err) {
      setBanner({ type: "error", text: err.message || "Lỗi khi kết nối hệ thống" });
    } finally {
      setLoading(false);
    }
  }, [search, startDate, endDate, cameraId, customerType, page, limit]);

  // Debounced Reload on Filters Change
  useEffect(() => {
    const timer = setTimeout(() => {
      loadLogs();
    }, 300);
    return () => clearTimeout(timer);
  }, [loadLogs]);

  // Auto Refresh Interval
  const refreshIntervalRef = useRef(null);
  useEffect(() => {
    if (autoRefresh) {
      refreshIntervalRef.current = setInterval(() => {
        loadLogs();
      }, 5000);
    } else {
      if (refreshIntervalRef.current) clearInterval(refreshIntervalRef.current);
    }
    return () => {
      if (refreshIntervalRef.current) clearInterval(refreshIntervalRef.current);
    };
  }, [autoRefresh, loadLogs]);

  // Handle Export CSV
  const handleExportCsv = async () => {
    setExporting(true);
    try {
      await exportRecognizeLogsCsv({
        search,
        startDate: startDate ? `${startDate} 00:00:00` : "",
        endDate: endDate ? `${endDate} 23:59:59` : "",
        cameraId,
        customerType,
      });
      setBanner({ type: "success", text: "Đã xuất file CSV lịch sử thành công!" });
    } catch (err) {
      setBanner({ type: "error", text: err.message || "Xuất CSV thất bại" });
    } finally {
      setExporting(false);
    }
  };

  // Helper Stats Calculation
  const vipCount = logs.filter((l) => l.customer_type !== "guest" && l.customer_type !== "temporary").length;
  const guestCount = logs.filter((l) => l.customer_type === "guest" || l.customer_type === "temporary" || !l.customer_type).length;

  return (
    <main className="h-dvh w-screen overflow-hidden bg-slate-50 text-slate-800">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="history" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-200">
          <PageHeader
            title="Lịch sử Nhận diện Real-Time"
            subtitle="Quản lý và tra cứu nhật ký nhận diện khuôn mặt từ hệ thống camera."
          />

          <div className="flex flex-1 min-h-0 flex-col overflow-y-auto p-4 md:p-6 space-y-4">
            <MessageBanner
              type={banner.type}
              message={banner.text}
              onClose={() => setBanner({ type: null, text: "" })}
            />

            {/* --- 1. METRICS BANNER --- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex items-center space-x-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-600 font-bold text-lg">
                  📊
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Tổng Sự Kiện</p>
                  <p className="text-xl font-bold text-slate-900">{totalCount.toLocaleString()}</p>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex items-center space-x-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 font-bold text-lg">
                  👑
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Khách Đăng Ký / VIP</p>
                  <p className="text-xl font-bold text-emerald-600">{vipCount}</p>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex items-center space-x-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-50 text-amber-600 font-bold text-lg">
                  👤
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Khách Mới (Guest)</p>
                  <p className="text-xl font-bold text-amber-600">{guestCount}</p>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex items-center space-x-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 font-bold text-lg">
                  📹
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Camera Đã Chọn</p>
                  <p className="text-xl font-bold text-indigo-600">
                    {cameraId === "all" ? cameras.length || "Tất cả" : 1}
                  </p>
                </div>
              </div>
            </div>

            {/* --- 2. FILTER TOOLBAR --- */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                {/* Search Box */}
                <div className="relative flex-1 min-w-[240px]">
                  <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(1);
                    }}
                    placeholder="Tìm tên khách, số điện thoại, mã ID..."
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-4 text-sm text-slate-800 outline-none focus:border-blue-500 focus:bg-white transition-all"
                  />
                </div>

                {/* Date Pickers */}
                <div className="flex items-center space-x-2">
                  <div className="flex items-center space-x-1 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-600">
                    <span>Từ:</span>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => {
                        setStartDate(e.target.value);
                        setPage(1);
                      }}
                      className="bg-transparent font-medium outline-none text-slate-800"
                    />
                  </div>
                  <div className="flex items-center space-x-1 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-600">
                    <span>Đến:</span>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => {
                        setEndDate(e.target.value);
                        setPage(1);
                      }}
                      className="bg-transparent font-medium outline-none text-slate-800"
                    />
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100 text-xs">
                {/* Camera & Type Selectors */}
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={cameraId}
                    onChange={(e) => {
                      setCameraId(e.target.value);
                      setPage(1);
                    }}
                    className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700 outline-none focus:border-blue-500 font-medium"
                  >
                    <option value="all">📷 Tất cả Camera</option>
                    {cameras.map((c) => (
                      <option key={c.camera_id} value={c.camera_id}>
                        {c.display_name || c.camera_id}
                      </option>
                    ))}
                  </select>

                  <select
                    value={customerType}
                    onChange={(e) => {
                      setCustomerType(e.target.value);
                      setPage(1);
                    }}
                    className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700 outline-none focus:border-blue-500 font-medium"
                  >
                    <option value="all">👥 Tất cả loại khách</option>
                    <option value="customer">👑 Khách Đăng Ký / VIP</option>
                    <option value="guest">👤 Khách Mới (Guest)</option>
                  </select>

                  {/* Reset Filter Button */}
                  {(search || startDate || endDate || cameraId !== "all" || customerType !== "all") && (
                    <button
                      onClick={() => {
                        setSearch("");
                        setStartDate("");
                        setEndDate("");
                        setCameraId("all");
                        setCustomerType("all");
                        setPage(1);
                      }}
                      className="text-slate-500 hover:text-red-600 underline font-medium px-2"
                    >
                      Xóa bộ lọc
                    </button>
                  )}
                </div>

                {/* Right Actions: Auto Refresh & CSV Export */}
                <div className="flex items-center space-x-3">
                  <label className="flex items-center space-x-2 cursor-pointer font-medium text-slate-600">
                    <input
                      type="checkbox"
                      checked={autoRefresh}
                      onChange={(e) => setAutoRefresh(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="flex items-center gap-1">
                      <span className={`h-2 w-2 rounded-full ${autoRefresh ? "bg-emerald-500 animate-ping" : "bg-slate-300"}`} />
                      Auto Refresh (5s)
                    </span>
                  </label>

                  <button
                    onClick={handleExportCsv}
                    disabled={exporting}
                    className="flex items-center space-x-1.5 rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50 transition-all shadow-sm"
                  >
                    <span>{exporting ? "⏳ Đang xuất..." : "📥 Xuất file CSV"}</span>
                  </button>
                </div>
              </div>
            </div>

            {/* --- 3. RECOGNITION LOGS TABLE --- */}
            <div className="flex-1 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
              <div className="flex-1 overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase tracking-wider text-slate-500 sticky top-0">
                    <tr>
                      <th className="px-5 py-3.5">Thời Gian</th>
                      <th className="px-5 py-3.5">Khách Hàng</th>
                      <th className="px-5 py-3.5">Loại Khách</th>
                      <th className="px-5 py-3.5">Camera / Nguồn</th>
                      <th className="px-5 py-3.5">Track ID</th>
                      <th className="px-5 py-3.5 text-right">Thao Tác</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {loading ? (
                      Array.from({ length: 5 }).map((_, i) => (
                        <tr key={i} className="animate-pulse">
                          <td className="px-5 py-4"><div className="h-4 w-28 bg-slate-200 rounded" /></td>
                          <td className="px-5 py-4"><div className="h-4 w-36 bg-slate-200 rounded" /></td>
                          <td className="px-5 py-4"><div className="h-4 w-20 bg-slate-200 rounded" /></td>
                          <td className="px-5 py-4"><div className="h-4 w-24 bg-slate-200 rounded" /></td>
                          <td className="px-5 py-4"><div className="h-4 w-12 bg-slate-200 rounded" /></td>
                          <td className="px-5 py-4 text-right"><div className="h-4 w-16 bg-slate-200 rounded ml-auto" /></td>
                        </tr>
                      ))
                    ) : logs.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-12 text-center text-slate-400">
                          <p className="text-3xl mb-2">🔍</p>
                          <p className="font-semibold text-slate-600">Không tìm thấy nhật ký nhận diện nào</p>
                          <p className="text-xs text-slate-400 mt-1">Thử điều chỉnh lại từ khóa hoặc khoảng thời gian lọc</p>
                        </td>
                      </tr>
                    ) : (
                      logs.map((log) => {
                        const isGuest = log.customer_type === "guest" || log.customer_type === "temporary" || !log.customer_type;
                        return (
                          <tr key={log.id} className="hover:bg-slate-50/80 transition-colors">
                            {/* Timestamp */}
                            <td className="px-5 py-3.5 whitespace-nowrap">
                              <span className="font-medium text-slate-900">
                                {new Date(log.timestamp).toLocaleTimeString("vi-VN")}
                              </span>
                              <span className="block text-xs text-slate-400">
                                {new Date(log.timestamp).toLocaleDateString("vi-VN")}
                              </span>
                            </td>

                            {/* Customer Name & Info */}
                            <td className="px-5 py-3.5">
                              <div className="flex items-center space-x-3">
                                <div
                                  className={`flex h-9 w-9 items-center justify-center rounded-xl font-bold text-xs ${
                                    isGuest ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"
                                  }`}
                                >
                                  {log.customer_name ? log.customer_name[0].toUpperCase() : "G"}
                                </div>
                                <div>
                                  <p className="font-semibold text-slate-900 leading-tight">
                                    {log.customer_name}
                                  </p>
                                  <p className="text-xs text-slate-400">
                                    {log.customer_phone || log.customer_id || "Chưa cập nhật"}
                                  </p>
                                </div>
                              </div>
                            </td>

                            {/* Customer Type Badge */}
                            <td className="px-5 py-3.5 whitespace-nowrap">
                              {isGuest ? (
                                <span className="inline-flex items-center rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700 border border-amber-200/60">
                                  👤 Khách mới (Guest)
                                </span>
                              ) : (
                                <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200/60">
                                  👑 {log.loyalty_tier || "Khách VIP"}
                                </span>
                              )}
                            </td>

                            {/* Camera Name */}
                            <td className="px-5 py-3.5 whitespace-nowrap">
                              <div className="flex items-center space-x-1.5 text-slate-700 font-medium text-xs">
                                <span>📷</span>
                                <span>{log.camera_name || log.camera_id}</span>
                              </div>
                            </td>

                            {/* Track ID */}
                            <td className="px-5 py-3.5 whitespace-nowrap font-mono text-xs text-slate-500">
                              #{log.track_id ?? "N/A"}
                            </td>

                            {/* Actions */}
                            <td className="px-5 py-3.5 text-right whitespace-nowrap">
                              <button
                                onClick={() => setSelectedLog(log)}
                                className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 hover:border-slate-300 transition-all shadow-2xs"
                              >
                                Chi tiết
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* --- 4. PAGINATION FOOTER --- */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-3 bg-slate-50 border-t border-slate-200 text-xs text-slate-600">
                <div className="flex items-center space-x-2">
                  <span>Hiển thị</span>
                  <select
                    value={limit}
                    onChange={(e) => {
                      setLimit(Number(e.target.value));
                      setPage(1);
                    }}
                    className="rounded-lg border border-slate-200 bg-white px-2 py-1 outline-none font-medium"
                  >
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </select>
                  <span>dòng / trang. Tổng số: <strong>{totalCount.toLocaleString()}</strong> bản ghi.</span>
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1 || loading}
                    className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40 transition-all"
                  >
                    ← Trang trước
                  </button>
                  <span className="font-semibold px-1">
                    Trang {page} / {totalPages}
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages || loading}
                    className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40 transition-all"
                  >
                    Trang sau →
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* --- 5. LOG DETAIL MODAL --- */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-fadeIn">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl space-y-4 border border-slate-100">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span>📋</span> Chi Tiết Sự Kiện Nhận Diện
              </h3>
              <button
                onClick={() => setSelectedLog(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-700">
              <div className="flex justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-400">Mã Log (ID):</span>
                <span className="font-mono font-medium">{selectedLog.id}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-400">Thời gian nhận diện:</span>
                <span className="font-semibold text-slate-900">
                  {new Date(selectedLog.timestamp).toLocaleString("vi-VN")}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-400">Mã Khách hàng (Customer ID):</span>
                <span className="font-mono font-semibold text-blue-600">{selectedLog.customer_id}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-400">Tên Khách hàng:</span>
                <span className="font-bold text-slate-900">{selectedLog.customer_name}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-400">Camera / Nguồn:</span>
                <span>{selectedLog.camera_name} ({selectedLog.camera_id})</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-50">
                <span className="text-slate-400">Track ID (Theo vết):</span>
                <span className="font-mono">#{selectedLog.track_id ?? "N/A"}</span>
              </div>
              {selectedLog.bbox && (
                <div className="py-1.5 border-b border-slate-50">
                  <span className="text-slate-400 block mb-1">Toạ độ Bounding Box (Khuôn mặt):</span>
                  <code className="block rounded bg-slate-100 p-2 font-mono text-[11px] text-slate-800">
                    {typeof selectedLog.bbox === "string" ? selectedLog.bbox : JSON.stringify(selectedLog.bbox)}
                  </code>
                </div>
              )}
            </div>

            <div className="pt-2 flex justify-end space-x-2">
              {selectedLog.customer_id && selectedLog.customer_type !== "guest" && (
                <a
                  href={`/customers/${selectedLog.customer_id}`}
                  className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 transition-colors shadow-sm"
                >
                  Xem Hồ Sơ Khách Hàng →
                </a>
              )}
              <button
                onClick={() => setSelectedLog(null)}
                className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 transition-colors"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
