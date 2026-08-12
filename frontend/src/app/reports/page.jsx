"use client";

import { useEffect, useState, useCallback } from "react";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import MessageBanner from "../../components/MessageBanner";
import { fetchReportsData, exportRecognizeLogsCsv, fetchCameras } from "../../services/api";

function LineChart({ data, xKey = "hour", yKey = "count", height = 220, color = "#3b82f6" }) {
  if (!data || data.length === 0) return null;

  const W = 600;
  const H = height;
  const PAD = { t: 25, r: 20, b: 35, l: 35 };

  const values = data.map((d) => d[yKey] || 0);
  const maxVal = Math.max(...values, 5);
  const iW = W - PAD.l - PAD.r;
  const iH = H - PAD.t - PAD.b;

  const pts = data.map((d, i) => ({
    x: PAD.l + (i / Math.max(1, data.length - 1)) * iW,
    y: PAD.t + iH - ((d[yKey] || 0) / maxVal) * iH,
    label: d[xKey],
    val: d[yKey] || 0,
  }));

  const pathD = pts
    .map((p, i) => {
      if (i === 0) return `M ${p.x} ${p.y}`;
      const cp = pts[i - 1];
      const mx = (cp.x + p.x) / 2;
      return `C ${mx} ${cp.y} ${mx} ${p.y} ${p.x} ${p.y}`;
    })
    .join(" ");

  const areaD = `${pathD} L ${pts[pts.length - 1].x} ${H - PAD.b} L ${pts[0].x} ${H - PAD.b} Z`;

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full overflow-visible font-sans">
        <defs>
          <linearGradient id={`grad_${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {[0, 0.5, 1].map((ratio, i) => {
          const y = PAD.t + iH * (1 - ratio);
          return (
            <g key={i}>
              <line x1={PAD.l} y1={y} x2={W - PAD.r} y2={y} stroke="#f1f5f9" strokeWidth="1" />
              <text x={PAD.l - 8} y={y + 3} textAnchor="end" className="text-[10px] fill-slate-400 font-medium">
                {Math.round(maxVal * ratio)}
              </text>
            </g>
          );
        })}

        {/* Area & Line */}
        <path d={areaD} fill={`url(#grad_${color.replace('#', '')})`} />
        <path d={pathD} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

        {/* Points & Labels */}
        {pts.map((p, i) => (
          <g key={i} className="group cursor-pointer">
            <circle
              cx={p.x}
              cy={p.y}
              r="4"
              fill="#ffffff"
              stroke={color}
              strokeWidth="2.5"
              className="transition-transform group-hover:scale-125"
            />
            {/* Tooltip on hover */}
            <text
              x={p.x}
              y={p.y - 10}
              textAnchor="middle"
              className="text-[10px] font-bold fill-slate-800 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              {p.val}
            </text>
            {/* X-axis labels */}
            <text x={p.x} y={H - 10} textAnchor="middle" className="text-[10px] fill-slate-400 font-medium">
              {p.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export default function ReportsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [banner, setBanner] = useState({ type: null, text: "" });

  // Filter States
  const [preset, setPreset] = useState("30days");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [cameraId, setCameraId] = useState("all");
  const [cameras, setCameras] = useState([]);

  // Load Cameras
  useEffect(() => {
    fetchCameras()
      .then((res) => setCameras(res.cameras || []))
      .catch(() => {});
  }, []);

  // Compute preset dates
  const applyPreset = useCallback((p) => {
    setPreset(p);
    const now = new Date();
    const formatYMD = (d) => d.toISOString().slice(0, 10);

    if (p === "today") {
      setStartDate(formatYMD(now));
      setEndDate(formatYMD(now));
    } else if (p === "7days") {
      const past = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      setStartDate(formatYMD(past));
      setEndDate(formatYMD(now));
    } else if (p === "30days") {
      const past = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      setStartDate(formatYMD(past));
      setEndDate(formatYMD(now));
    } else {
      // Custom - do not override
    }
  }, []);

  useEffect(() => {
    applyPreset("30days");
  }, [applyPreset]);

  // Fetch Reports Data
  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchReportsData({
        startDate: startDate ? `${startDate} 00:00:00` : "",
        endDate: endDate ? `${endDate} 23:59:59` : "",
        cameraId,
      });

      if (res.success) {
        setData(res.data);
      } else {
        setBanner({ type: "error", text: res.message || "Không thể nạp dữ liệu thống kê" });
      }
    } catch (err) {
      setBanner({ type: "error", text: err.message || "Lỗi kết nối hệ thống" });
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, cameraId]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  // Handle Export CSV
  const handleExportCsv = async () => {
    setExporting(true);
    try {
      await exportRecognizeLogsCsv({
        startDate: startDate ? `${startDate} 00:00:00` : "",
        endDate: endDate ? `${endDate} 23:59:59` : "",
        cameraId,
      });
      setBanner({ type: "success", text: "Đã xuất file báo cáo CSV thành công!" });
    } catch (err) {
      setBanner({ type: "error", text: err.message || "Xuất file thất bại" });
    } finally {
      setExporting(false);
    }
  };

  const summary = data?.summary || {
    total_visits: 0,
    vip_visits: 0,
    guest_visits: 0,
    unique_customers: 0,
    repeat_rate: 0.0,
    peak_hour: "12h",
    peak_count: 0,
  };

  return (
    <main className="h-dvh w-screen overflow-hidden bg-slate-50 text-slate-800">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="reports" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-200">
          <PageHeader
            title="Báo cáo & Thống kê F&B"
            subtitle="Phân tích lưu lượng khách hàng, giờ cao điểm và tỷ lệ khách thân thiết thực tế từ cơ sở dữ liệu."
          />

          <div className="flex flex-1 min-h-0 flex-col overflow-y-auto p-4 md:p-6 space-y-5">
            <MessageBanner
              type={banner.type}
              message={banner.text}
              onClose={() => setBanner({ type: null, text: "" })}
            />

            {/* --- 1. FILTER BAR --- */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
              {/* Preset Pills */}
              <div className="flex items-center space-x-1.5 bg-slate-100 p-1 rounded-xl">
                {[
                  { id: "today", label: "Hôm nay" },
                  { id: "7days", label: "7 ngày qua" },
                  { id: "30days", label: "30 ngày qua" },
                  { id: "custom", label: "Tùy chỉnh" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => applyPreset(item.id)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                      preset === item.id ? "bg-white text-slate-900 shadow-2xs" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              {/* Custom Date Pickers & Camera Select */}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {preset === "custom" && (
                  <div className="flex items-center space-x-2">
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 font-medium outline-none"
                    />
                    <span>–</span>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 font-medium outline-none"
                    />
                  </div>
                )}

                <select
                  value={cameraId}
                  onChange={(e) => setCameraId(e.target.value)}
                  className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-slate-700 outline-none font-medium"
                >
                  <option value="all">📷 Tất cả Camera</option>
                  {cameras.map((c) => (
                    <option key={c.camera_id} value={c.camera_id}>
                      {c.display_name || c.camera_id}
                    </option>
                  ))}
                </select>

                <button
                  onClick={handleExportCsv}
                  disabled={exporting}
                  className="flex items-center space-x-1.5 rounded-xl bg-slate-900 px-4 py-2 font-semibold text-white hover:bg-slate-800 disabled:opacity-50 transition-all shadow-sm"
                >
                  <span>{exporting ? "⏳ Đang xuất..." : "📥 Xuất Báo Cáo CSV"}</span>
                </button>
              </div>
            </div>

            {/* --- 2. EXECUTIVE KPI CARDS --- */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider">Tổng Lượt Khách</span>
                  <span className="text-lg">📊</span>
                </div>
                <p className="text-2xl font-bold text-slate-900">
                  {loading ? "..." : summary.total_visits.toLocaleString()}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Đại diện cho {summary.unique_customers} khách duy nhất
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider">Tỷ Lệ Khách Quay Lại</span>
                  <span className="text-lg">🔁</span>
                </div>
                <p className="text-2xl font-bold text-emerald-600">
                  {loading ? "..." : `${summary.repeat_rate}%`}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  {summary.vip_visits} lượt khách cũ / VIP
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider">Giờ Cao Điểm Nhất</span>
                  <span className="text-lg">⏰</span>
                </div>
                <p className="text-2xl font-bold text-blue-600">
                  {loading ? "..." : summary.peak_hour}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  {summary.peak_count} lượt khách trong giờ cao điểm
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider">Khách Mới (Guest)</span>
                  <span className="text-lg">👤</span>
                </div>
                <p className="text-2xl font-bold text-amber-600">
                  {loading ? "..." : summary.guest_visits.toLocaleString()}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Khách vãng lai / Lần đầu ghé
                </p>
              </div>
            </div>

            {/* --- 3. CHARTS SECTION --- */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Hourly Traffic Flow Chart */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <h3 className="font-bold text-slate-900 text-sm">Lưu Lượng Khách Theo Giờ (F&B Hourly Traffic Flow)</h3>
                    <p className="text-xs text-slate-500">Giúp tối ưu hóa ca làm việc của nhân viên pha chế & phục vụ</p>
                  </div>
                  <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-semibold text-blue-600">
                    Peak: {summary.peak_hour}
                  </span>
                </div>

                {loading ? (
                  <div className="h-48 flex items-center justify-center text-slate-400 text-xs">Đang nạp biểu đồ...</div>
                ) : (
                  <LineChart data={data?.hourly_traffic || []} xKey="hour" yKey="count" color="#3b82f6" />
                )}
              </div>

              {/* Daily Traffic Trend Chart */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <h3 className="font-bold text-slate-900 text-sm">Xu Hướng Lưu Lượng Theo Ngày</h3>
                    <p className="text-xs text-slate-500">Theo dõi sự biến động lượng khách qua từng ngày</p>
                  </div>
                  <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-600">
                    7 Ngày Qua
                  </span>
                </div>

                {loading ? (
                  <div className="h-48 flex items-center justify-center text-slate-400 text-xs">Đang nạp biểu đồ...</div>
                ) : (
                  <LineChart data={data?.daily_traffic || []} xKey="day" yKey="count" color="#10b981" />
                )}
              </div>
            </div>

            {/* --- 4. LOYALTY TIER & TOP CUSTOMERS --- */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
              {/* Loyalty Tier Distribution */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                <h3 className="font-bold text-slate-900 text-sm border-b border-slate-100 pb-3">
                  Cơ Cấu Hạng Thành Viên
                </h3>

                <div className="space-y-3">
                  {(data?.loyalty_distribution || [
                    { tier: "VIP", count: summary.vip_visits },
                    { tier: "Guest", count: summary.guest_visits },
                  ]).map((item, idx) => {
                    const pct = summary.total_visits > 0 ? Math.round((item.count / summary.total_visits) * 100) : 0;
                    return (
                      <div key={idx} className="space-y-1">
                        <div className="flex justify-between text-xs font-semibold">
                          <span className="text-slate-700">{item.tier}</span>
                          <span className="text-slate-500">{item.count} lượt ({pct}%)</span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-blue-600 transition-all duration-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Top Regular Customers Table */}
              <div className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <h3 className="font-bold text-slate-900 text-sm">Top Khách Hàng Thân Thiết Nhất</h3>
                  <span className="text-xs text-slate-500">Xếp theo số lượt ghé thăm</span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-slate-700">
                    <thead className="bg-slate-50 text-slate-500 uppercase font-semibold">
                      <tr>
                        <th className="px-4 py-2.5">Khách Hàng</th>
                        <th className="px-4 py-2.5">Số Điện Thoại</th>
                        <th className="px-4 py-2.5">Hạng Thẻ</th>
                        <th className="px-4 py-2.5 text-center">Số Lượt Ghé</th>
                        <th className="px-4 py-2.5 text-right">Lần Cuối Ghé</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {loading ? (
                        <tr><td colSpan={5} className="py-6 text-center text-slate-400">Đang nạp...</td></tr>
                      ) : (data?.top_customers || []).length === 0 ? (
                        <tr><td colSpan={5} className="py-6 text-center text-slate-400">Chưa có dữ liệu khách thân thiết</td></tr>
                      ) : (
                        (data?.top_customers || []).map((c, i) => (
                          <tr key={c.id || i} className="hover:bg-slate-50 transition-colors">
                            <td className="px-4 py-3 font-bold text-slate-900">{c.name}</td>
                            <td className="px-4 py-3 text-slate-500">{c.phone || "Chưa có"}</td>
                            <td className="px-4 py-3">
                              <span className="inline-flex rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">
                                {c.loyalty_tier}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-center font-bold text-blue-600">{c.visit_count}</td>
                            <td className="px-4 py-3 text-right text-slate-400">
                              {c.last_seen ? new Date(c.last_seen).toLocaleDateString("vi-VN") : "N/A"}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
