"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Sidebar from "../../../components/Sidebar";
import PageHeader from "../../../components/PageHeader";
import { ArrowLeft, Calendar, Phone, FileText } from "lucide-react";
import { fetchCustomerProfileById } from "../../../services/api";

function rankLabel(visitCount) {
  const n = Number(visitCount || 0);
  if (n >= 30) return "VIP";
  if (n >= 10) return "Member";
  return "Guest";
}

function rankPill(rank) {
  if (rank === "VIP") return "bg-yellow-50 text-yellow-700 border-yellow-200";
  if (rank === "Member") return "bg-blue-50 text-blue-700 border-blue-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function rankStars(rank) {
  if (rank === "VIP") return 5;
  if (rank === "Member") return 4;
  return 3;
}

function formatDate(dateStr) {
  if (!dateStr) return "—";
  try {
    const dt = new Date(dateStr.replace(" ", "T"));
    if (isNaN(dt.getTime())) return dateStr;
    const now = new Date();
    const yesterday = new Date();
    yesterday.setDate(now.getDate() - 1);
    if (dt.toDateString() === now.toDateString()) return "Hôm nay";
    if (dt.toDateString() === yesterday.toDateString()) return "Hôm qua";
    return dt.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch { return dateStr; }
}

function formatTime(dateStr) {
  if (!dateStr) return "—";
  try {
    const dt = new Date(dateStr.replace(" ", "T"));
    if (isNaN(dt.getTime())) return "—";
    return dt.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch { return "—"; }
}

function formatDateTime(dateStr) {
  if (!dateStr) return "—";
  return `${formatDate(dateStr)}, ${formatTime(dateStr)}`;
}

function Stars({ count }) {
  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <svg key={i} viewBox="0 0 14 14" className={`h-4 w-4 ${i < count ? "fill-amber-400" : "fill-slate-200"}`}>
          <path d="M7 1l1.6 3.4 3.7.5-2.7 2.6.6 3.7L7 9.5l-3.2 1.7.6-3.7L1.7 4.9l3.7-.5z" />
        </svg>
      ))}
    </div>
  );
}

export default function CustomerDetailPage() {
  const params = useParams();
  const id = params?.id;

  const [customer, setCustomer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;

    // 1) Try to load prefetched profile from sessionStorage (set by dashboard)
    let usedPrefetch = false;
    try {
      const key = `prefetch_profile_${id}`;
      const cached = sessionStorage.getItem(key);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed && parsed.id) {
          setCustomer(parsed);
          setLoading(false);
          usedPrefetch = true;
        }
        // Consume it so stale data doesn't persist on reload
        sessionStorage.removeItem(key);
      }
    } catch (_) {}

    // 2) Always fetch from API (either as primary or as background re-validation)
    fetchCustomerProfileById(id)
      .then((data) => {
        if (data.status === "success") {
          setCustomer(data.customer);
        } else if (!usedPrefetch) {
          setError(data.message || "Không tìm thấy khách hàng.");
        }
      })
      .catch((err) => {
        if (!usedPrefetch) setError(err.message || "Không thể kết nối tới backend.");
      })
      .finally(() => setLoading(false));
  }, [id]);

  const rank = customer ? rankLabel(customer.visit_count) : "Guest";
  const stars = rankStars(rank);
  const displayId = id
    ? (String(id).startsWith("GUEST_") ? id : `CLIENT_${id}`)
    : "—";

  const statCards = customer
    ? [
      { label: "Tổng lượt ghé", value: String(customer.visit_count ?? 0) },
      { label: "Lần gần nhất", value: formatDate(customer.last_visit) },
      { label: "Số điện thoại", value: customer.phone || "Chưa có" },
      { label: "Hạng", value: rank },
    ]
    : [];

  return (
    <main className="min-h-screen bg-slate-50 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-[1400px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="customers" />

        <div className="flex min-w-0 flex-col">
          <PageHeader
            title="Hồ sơ Khách hàng"
            subtitle="Thông tin chi tiết và lịch sử của khách hàng."
          />

          <div className="flex-1 p-6">
            {loading ? (
              <div className="flex h-48 items-center justify-center text-sm text-slate-400">
                Đang tải hồ sơ khách hàng...
              </div>
            ) : error ? (
              <div className="flex h-48 flex-col items-center justify-center gap-3">
                <p className="text-sm text-red-500">{error}</p>
                <Link href="/customers" className="text-sm text-blue-600 hover:underline">
                  ← Quay lại danh sách
                </Link>
              </div>
            ) : (
              <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">

                {/* ── Left column ─────────────────────────────────────── */}
                <div className="flex flex-col gap-4">

                  {/* Profile card */}
                  <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <Link href="/customers" className="mb-5 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800">
                      <ArrowLeft className="h-4 w-4" />
                      Quay lại
                    </Link>

                    <div className="flex flex-col items-center gap-3 text-center">
                      {/* Avatar */}
                      <div className="h-20 w-20 overflow-hidden rounded-full border-4 border-slate-100 bg-gradient-to-br from-blue-100 to-slate-200 shadow-sm">
                        <div className="h-full w-full bg-gradient-to-br from-blue-200 to-indigo-300" />
                      </div>

                      <div>
                        <h2 className="text-lg font-semibold text-slate-900">
                          {customer.name || "Khách mời"}
                        </h2>
                        <p className="text-sm text-slate-400">{displayId}</p>
                      </div>

                      <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${rankPill(rank)}`}>
                        {rank}
                      </span>
                      <Stars count={stars} />
                    </div>

                    {/* Meta rows */}
                    <div className="mt-5 space-y-3">
                      <div className="flex items-center gap-2.5 text-sm text-slate-600">
                        <Calendar className="h-4 w-4 shrink-0 text-slate-400" />
                        <div>
                          <div className="text-xs text-slate-400">Lần gần nhất</div>
                          <div className="font-medium">{formatDateTime(customer.last_visit)}</div>
                        </div>
                      </div>

                      {customer.phone && (
                        <div className="flex items-center gap-2.5 text-sm text-slate-600">
                          <Phone className="h-4 w-4 shrink-0 text-slate-400" />
                          <div>
                            <div className="text-xs text-slate-400">Số điện thoại</div>
                            <div className="font-medium">{customer.phone}</div>
                          </div>
                        </div>
                      )}

                      {customer.note && (
                        <div className="flex items-start gap-2.5 text-sm text-slate-600">
                          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                          <div>
                            <div className="text-xs text-slate-400">Ghi chú</div>
                            <div className="font-medium">{customer.note}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Face samples */}
                  <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h3 className="mb-3 text-sm font-semibold text-slate-800">Mẫu khuôn mặt</h3>
                    <div className="flex gap-2">
                      {[0, 1, 2].map((i) => (
                        <div
                          key={i}
                          className="h-16 w-16 overflow-hidden rounded-xl bg-gradient-to-br from-slate-200 to-slate-300"
                        />
                      ))}
                    </div>
                  </div>
                </div>

                {/* ── Right column ─────────────────────────────────────── */}
                <div className="flex flex-col gap-5">

                  {/* Stat cards */}
                  <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                    {statCards.map((s) => (
                      <div key={s.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                        <p className="text-xs text-slate-400">{s.label}</p>
                        <p className="mt-1 text-xl font-bold text-slate-900">{s.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Visit history */}
                  <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="border-b border-slate-100 px-5 py-4">
                      <h3 className="text-sm font-semibold text-slate-800">Lịch sử ghé thăm</h3>
                    </div>
                    <table className="w-full table-auto text-left">
                      <thead>
                        <tr className="border-b border-slate-100">
                          {["Ngày", "Thời gian", "Tổng lượt", "Trạng thái"].map((col) => (
                            <th key={col} className="px-5 py-3 text-xs font-medium text-slate-400">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {customer.last_visit ? (
                          <tr className="hover:bg-slate-50/60">
                            <td className="px-5 py-3.5 text-sm text-slate-700">{formatDate(customer.last_visit)}</td>
                            <td className="px-5 py-3.5 text-sm text-slate-700">{formatTime(customer.last_visit)}</td>
                            <td className="px-5 py-3.5 text-sm text-slate-700">{customer.visit_count ?? 0} lần</td>
                            <td className="px-5 py-3.5">
                              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-600">
                                Hoàn thành
                              </span>
                            </td>
                          </tr>
                        ) : (
                          <tr>
                            <td colSpan={4} className="px-5 py-6 text-center text-sm text-slate-400">
                              Chưa có lịch sử ghé thăm.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
