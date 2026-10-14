"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import { Search, SlidersHorizontal, ChevronDown } from "lucide-react";
import { fetchAllCustomers } from "../../services/api";
import { useCustomerDetection } from "../../hooks/useCustomerDetection";
import { useApp } from "../../context/AppContext";

const RANK_PILL = {
  VIP: "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950/60 dark:text-yellow-400 dark:border-yellow-800/60",
  Member: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/60 dark:text-blue-400 dark:border-blue-800/60",
  Guest: "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
};

const STATUS_PILL = {
  present: "text-emerald-600 bg-emerald-50 dark:bg-emerald-950/60 dark:text-emerald-400",
  departed: "text-slate-500 bg-transparent dark:text-slate-400",
  pending: "text-amber-600 bg-amber-50 dark:bg-amber-950/60 dark:text-amber-400",
};

function Stars({ count }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <svg
          key={i}
          viewBox="0 0 12 12"
          className={`h-3.5 w-3.5 ${i < count ? "fill-amber-400" : "fill-slate-200 dark:fill-slate-700"}`}
        >
          <path d="M6 1l1.4 2.9 3.2.5-2.3 2.2.5 3.2L6 8.2l-2.8 1.6.5-3.2L1.4 4.4l3.2-.5z" />
        </svg>
      ))}
    </div>
  );
}

function rankLabel(visitCount) {
  const n = Number(visitCount || 0);
  if (n >= 30) return "VIP";
  if (n >= 10) return "Member";
  return "Guest";
}

function formatLastVisit(dateStr, lang = "en") {
  if (!dateStr) return lang === "vi" ? "Chưa từng" : "Never";
  try {
    const dt = new Date(dateStr.replace(" ", "T"));
    if (isNaN(dt.getTime())) return dateStr;

    const now = new Date();
    const isToday = dt.toDateString() === now.toDateString();

    const yesterday = new Date();
    yesterday.setDate(now.getDate() - 1);
    const isYesterday = dt.toDateString() === yesterday.toDateString();

    const isVi = lang === "vi";
    const timeStr = dt.toLocaleTimeString(isVi ? "vi-VN" : "en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });

    if (isToday) return isVi ? `Hôm nay, ${timeStr}` : `Today, ${timeStr}`;
    if (isYesterday) return isVi ? `Hôm qua, ${timeStr}` : `Yesterday, ${timeStr}`;

    return (
      dt.toLocaleDateString(isVi ? "vi-VN" : "en-US", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      }) + `, ${timeStr}`
    );
  } catch {
    return dateStr;
  }
}

export default function CustomersPage() {
  const router = useRouter();
  const { t, lang } = useApp();
  const [role, setRole] = useState(null);
  const [tab, setTab] = useState("all");
  const [query, setQuery] = useState("");
  const [dbCustomers, setDbCustomers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const { customers: liveCustomers } = useCustomerDetection();

  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    if (savedRole !== "admin") {
      router.push("/");
      return;
    }
    setRole(savedRole);
  }, [router]);

  useEffect(() => {
    if (role !== "admin") return;
    let active = true;
    async function load() {
      try {
        const res = await fetchAllCustomers();
        if (res.status === "success" && active) {
          setDbCustomers(res.customers || []);
        }
      } catch (err) {
        console.error("Failed to load customers:", err);
      } finally {
        if (active) setIsLoading(false);
      }
    }
    load();
    const interval = setInterval(load, 4000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [role]);

  if (role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
        <p className="text-slate-500 font-medium">{t("redirecting")}</p>
      </div>
    );
  }

  // Map database customers to UI structures
  const mappedCustomers = dbCustomers.map((c) => {
    const isPresent = liveCustomers.some((lc) => lc.id === c.id);
    let statusCode = "departed";
    const isGuest = c.id.startsWith("GUEST_") || c.id.startsWith("LN");
    if (isPresent) {
      statusCode = "present";
    } else if (isGuest) {
      statusCode = "pending";
    }

    const rank = rankLabel(c.visit_count);
    const displayId = isGuest ? c.id : `CLIENT_${c.id}`;

    return {
      id: c.id,
      displayId,
      name: c.name || (lang === "vi" ? "Khách mời" : "Guest"),
      visits: c.visit_count || 0,
      rank,
      stars: rank === "VIP" ? 5 : rank === "Member" ? 4 : 3,
      lastVisit: formatLastVisit(c.last_visit, lang),
      statusCode,
      statusLabel: statusCode === "present" ? t("in_venue") : statusCode === "pending" ? t("pending_verification") : t("departed"),
    };
  });

  const filtered = mappedCustomers.filter((c) => {
    if (
      query &&
      !c.name.toLowerCase().includes(query.toLowerCase()) &&
      !c.id.toLowerCase().includes(query.toLowerCase())
    )
      return false;
    if (tab === "present") return c.statusCode === "present";
    if (tab === "pending") return c.statusCode === "pending";
    if (tab === "vip") return c.rank === "VIP";
    return true;
  });

  const allCount = mappedCustomers.length;
  const presentCount = mappedCustomers.filter((c) => c.statusCode === "present").length;
  const pendingCount = mappedCustomers.filter((c) => c.statusCode === "pending").length;
  const vipCount = mappedCustomers.filter((c) => c.rank === "VIP").length;

  const tabs = [
    { key: "all", label: t("all_filter"), count: allCount },
    { key: "present", label: t("in_venue"), count: presentCount },
    { key: "pending", label: t("pending_verification"), count: pendingCount },
    { key: "vip", label: "VIP", count: vipCount },
  ];

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white dark:bg-slate-950 transition-colors duration-200">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="customers" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
          <PageHeader
            title={t("customers_title")}
            subtitle={lang === "vi" ? "Danh sách toàn bộ khách hàng được nhận diện bởi hệ thống." : "Directory of all customers identified across camera streams."}
          />

          <div className="flex flex-1 min-h-0 flex-col p-4 sm:p-5 lg:p-6">
            {/* Search + filter bar */}
            <div className="mb-4 flex shrink-0 items-center gap-3">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t("search_customers_placeholder")}
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 py-2.5 pl-9 pr-4 text-sm text-slate-800 dark:text-slate-100 outline-none placeholder:text-slate-400 focus:border-blue-400"
                />
              </div>
              <div className="ml-auto flex items-center gap-2">
                <button className="flex items-center gap-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800">
                  <SlidersHorizontal className="h-4 w-4" />
                  {t("filter_btn")}
                </button>
                <button className="flex items-center gap-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800">
                  {t("today_filter")}
                  <ChevronDown className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Tabs */}
            <div className="mb-5 flex shrink-0 items-center gap-2">
              {tabs.map((tb) => (
                <button
                  key={tb.key}
                  onClick={() => setTab(tb.key)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    tab === tb.key
                      ? "bg-blue-600 text-white shadow-sm"
                      : "border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                  }`}
                >
                  {tb.label} <span className="ml-1 opacity-70">({tb.count})</span>
                </button>
              ))}
            </div>

            {/* Table */}
            <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
              {isLoading ? (
                <div className="px-5 py-8 text-center text-sm text-slate-400 animate-pulse">
                  {t("loading_customers")}
                </div>
              ) : filtered.length === 0 ? (
                <div className="px-5 py-8 text-center text-sm text-slate-400">
                  {t("no_customers_found")}
                </div>
              ) : (
                <table className="w-full min-w-[700px] table-auto text-left">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-850/50">
                      {[
                        t("col_customer"),
                        t("col_id"),
                        t("col_rank"),
                        t("col_visits"),
                        t("col_last_visit"),
                        t("col_rating"),
                        t("col_status"),
                      ].map((col) => (
                        <th
                          key={col}
                          className="px-5 py-3.5 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {filtered.map((c) => (
                      <tr key={c.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/50 transition-colors">
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-blue-900/60 dark:to-indigo-900/60 text-xs font-bold text-blue-600 dark:text-blue-300">
                              {c.name.charAt(0)}
                            </div>
                            <Link
                              href={`/customers/${c.id}`}
                              className="text-sm font-semibold text-slate-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                            >
                              {c.name}
                            </Link>
                          </div>
                        </td>
                        <td className="px-5 py-4 text-sm font-mono text-slate-500 dark:text-slate-400">
                          {c.displayId}
                        </td>
                        <td className="px-5 py-4">
                          <span
                            className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${RANK_PILL[c.rank]}`}
                          >
                            {c.rank}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                          {c.visits}
                        </td>
                        <td className="px-5 py-4 text-sm text-slate-500 dark:text-slate-400">
                          {c.lastVisit}
                        </td>
                        <td className="px-5 py-4">
                          <Stars count={c.stars} />
                        </td>
                        <td className="px-5 py-4">
                          <span
                            className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_PILL[c.statusCode]}`}
                          >
                            {c.statusLabel}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
