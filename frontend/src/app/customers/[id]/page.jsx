"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Sidebar from "../../../components/Sidebar";
import PageHeader from "../../../components/PageHeader";
import { ArrowLeft, Calendar, Phone, FileText } from "lucide-react";
import { fetchCustomerProfileById } from "../../../services/api";
import { useApp } from "../../../context/AppContext";

function rankLabel(visitCount) {
  const n = Number(visitCount || 0);
  if (n >= 30) return "VIP";
  if (n >= 10) return "Member";
  return "Guest";
}

function rankPill(rank) {
  if (rank === "VIP") return "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950/60 dark:text-yellow-400 dark:border-yellow-800/60";
  if (rank === "Member") return "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/60 dark:text-blue-400 dark:border-blue-800/60";
  return "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700";
}

function formatDate(dateStr, lang = "en") {
  if (!dateStr) return "—";
  try {
    const dt = new Date(dateStr.replace(" ", "T"));
    if (isNaN(dt.getTime())) return dateStr;
    const now = new Date();
    const yesterday = new Date();
    yesterday.setDate(now.getDate() - 1);
    const isVi = lang === "vi";
    if (dt.toDateString() === now.toDateString()) return isVi ? "Hôm nay" : "Today";
    if (dt.toDateString() === yesterday.toDateString()) return isVi ? "Hôm qua" : "Yesterday";
    return dt.toLocaleDateString(isVi ? "vi-VN" : "en-US", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

function formatTime(dateStr, lang = "en") {
  if (!dateStr) return "—";
  try {
    const dt = new Date(dateStr.replace(" ", "T"));
    if (isNaN(dt.getTime())) return "—";
    return dt.toLocaleTimeString(lang === "vi" ? "vi-VN" : "en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "—";
  }
}

function formatDateTime(dateStr, lang = "en") {
  if (!dateStr) return "—";
  return `${formatDate(dateStr, lang)}, ${formatTime(dateStr, lang)}`;
}

function Stars({ count }) {
  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <svg
          key={i}
          viewBox="0 0 14 14"
          className={`h-4 w-4 ${i < count ? "fill-amber-400" : "fill-slate-200 dark:fill-slate-700"}`}
        >
          <path d="M7 1l1.6 3.4 3.7.5-2.7 2.6.6 3.7L7 9.5l-3.2 1.7.6-3.7L1.7 4.9l3.7-.5z" />
        </svg>
      ))}
    </div>
  );
}

export default function CustomerDetailPage() {
  const params = useParams();
  const id = params?.id;
  const { t, lang } = useApp();

  const [customer, setCustomer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;

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
        sessionStorage.removeItem(key);
      }
    } catch (_) {}

    fetchCustomerProfileById(id)
      .then((data) => {
        if (data.status === "success") {
          setCustomer(data.customer);
        } else if (!usedPrefetch) {
          setError(data.message || (lang === "vi" ? "Không tìm thấy khách hàng." : "Customer not found."));
        }
      })
      .catch((err) => {
        if (!usedPrefetch)
          setError(err.message || (lang === "vi" ? "Không thể kết nối tới backend." : "Cannot connect to server."));
      })
      .finally(() => setLoading(false));
  }, [id, lang]);

  const rank = customer ? rankLabel(customer.visit_count) : "Guest";
  const stars = rank === "VIP" ? 5 : rank === "Member" ? 4 : 3;
  const isGuestId = id && (String(id).startsWith("GUEST_") || String(id).startsWith("LN"));
  const displayId = id
    ? isGuestId
      ? id
      : `CLIENT_${id}`
    : "—";

  const statCards = customer
    ? [
        { label: t("total_visits_stat"), value: String(customer.visit_count ?? 0) },
        { label: t("last_visit_stat"), value: formatDate(customer.last_visit, lang) },
        { label: t("phone_stat"), value: customer.phone || t("not_provided") },
        { label: t("col_rank"), value: rank },
      ]
    : [];

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white dark:bg-slate-950 transition-colors duration-200">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="customers" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
          <PageHeader
            title={t("customer_profile_title")}
            subtitle={t("customer_profile_subtitle")}
          />

          <div className="flex-1 overflow-y-auto p-4 sm:p-6">
            {loading ? (
              <div className="flex h-48 items-center justify-center text-sm text-slate-400 animate-pulse">
                {lang === "vi" ? "Đang tải hồ sơ khách hàng..." : "Loading customer profile..."}
              </div>
            ) : error ? (
              <div className="flex h-48 flex-col items-center justify-center gap-3">
                <p className="text-sm text-red-500">{error}</p>
                <Link
                  href="/customers"
                  className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline"
                >
                  {t("back_to_list")}
                </Link>
              </div>
            ) : (
              <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
                {/* ── Left column ─────────────────────────────────────── */}
                <div className="flex flex-col gap-4">
                  {/* Profile card */}
                  <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
                    <Link
                      href="/customers"
                      className="mb-5 flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
                    >
                      <ArrowLeft className="h-4 w-4" />
                      {t("back")}
                    </Link>

                    <div className="flex flex-col items-center gap-3 text-center">
                      {/* Avatar */}
                      <div className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-slate-100 dark:border-slate-800 bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-blue-900 dark:to-indigo-900 text-2xl font-bold text-blue-600 dark:text-blue-300 shadow-sm">
                        {(customer.name || "G").charAt(0)}
                      </div>

                      <div>
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                          {customer.name || (lang === "vi" ? "Khách mời" : "Guest")}
                        </h2>
                        <p className="text-xs font-mono text-slate-400 dark:text-slate-500">{displayId}</p>
                      </div>

                      <span
                        className={`rounded-full border px-3 py-1 text-xs font-semibold ${rankPill(rank)}`}
                      >
                        {rank}
                      </span>
                      <Stars count={stars} />
                    </div>

                    {/* Meta rows */}
                    <div className="mt-5 space-y-3.5 border-t border-slate-100 dark:border-slate-800/80 pt-4">
                      <div className="flex items-center gap-2.5 text-sm text-slate-600 dark:text-slate-300">
                        <Calendar className="h-4 w-4 shrink-0 text-slate-400" />
                        <div>
                          <div className="text-xs text-slate-400 dark:text-slate-500">
                            {t("last_visit_stat")}
                          </div>
                          <div className="font-semibold text-slate-800 dark:text-slate-200">
                            {formatDateTime(customer.last_visit, lang)}
                          </div>
                        </div>
                      </div>

                      {customer.phone && (
                        <div className="flex items-center gap-2.5 text-sm text-slate-600 dark:text-slate-300">
                          <Phone className="h-4 w-4 shrink-0 text-slate-400" />
                          <div>
                            <div className="text-xs text-slate-400 dark:text-slate-500">
                              {t("phone_stat")}
                            </div>
                            <div className="font-semibold text-slate-800 dark:text-slate-200">{customer.phone}</div>
                          </div>
                        </div>
                      )}

                      {customer.note && (
                        <div className="flex items-start gap-2.5 text-sm text-slate-600 dark:text-slate-300">
                          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                          <div>
                            <div className="text-xs text-slate-400 dark:text-slate-500">
                              {t("notes")}
                            </div>
                            <div className="font-medium text-slate-800 dark:text-slate-200">{customer.note}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Face samples */}
                  <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
                    <h3 className="mb-3 text-sm font-semibold text-slate-800 dark:text-white">
                      {t("face_samples")}
                    </h3>
                    <div className="flex gap-2">
                      {[0, 1, 2].map((i) => (
                        <div
                          key={i}
                          className="flex h-16 w-16 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-[10px] text-slate-400"
                        >
                          Face #{i + 1}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* ── Right column ─────────────────────────────────────── */}
                <div className="flex flex-col gap-5">
                  {/* Stat cards */}
                  <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                    {statCards.map((s) => (
                      <div
                        key={s.label}
                        className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm"
                      >
                        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{s.label}</p>
                        <p className="mt-1 text-xl font-bold text-slate-900 dark:text-white font-display">
                          {s.value}
                        </p>
                      </div>
                    ))}
                  </div>

                  {/* Visit history */}
                  <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
                    <div className="border-b border-slate-100 dark:border-slate-800 px-5 py-4">
                      <h3 className="text-sm font-semibold text-slate-800 dark:text-white">
                        {t("visit_history")}
                      </h3>
                    </div>
                    <table className="w-full table-auto text-left">
                      <thead>
                        <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-850/50">
                          {[t("col_date"), t("col_time"), t("col_total_visits"), t("col_status")].map(
                            (col) => (
                              <th
                                key={col}
                                className="px-5 py-3 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider"
                              >
                                {col}
                              </th>
                            ),
                          )}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                        {customer.last_visit ? (
                          <tr className="hover:bg-slate-50/80 dark:hover:bg-slate-800/50 transition-colors">
                            <td className="px-5 py-3.5 text-sm font-medium text-slate-800 dark:text-slate-200">
                              {formatDate(customer.last_visit, lang)}
                            </td>
                            <td className="px-5 py-3.5 text-sm font-mono text-slate-600 dark:text-slate-400">
                              {formatTime(customer.last_visit, lang)}
                            </td>
                            <td className="px-5 py-3.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
                              {customer.visit_count ?? 0} {lang === "vi" ? "lần" : "visits"}
                            </td>
                            <td className="px-5 py-3.5">
                              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
                                {t("completed")}
                              </span>
                            </td>
                          </tr>
                        ) : (
                          <tr>
                            <td
                              colSpan={4}
                              className="px-5 py-6 text-center text-sm text-slate-400"
                            >
                              {t("no_history")}
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
