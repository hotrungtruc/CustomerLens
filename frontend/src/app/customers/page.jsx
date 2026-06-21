"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import { Search, SlidersHorizontal, ChevronDown } from "lucide-react";
import { fetchAllCustomers } from "../../services/api";
import { useCustomerDetection } from "../../hooks/useCustomerDetection";

const RANK_PILL = {
  VIP: "bg-yellow-50 text-yellow-700 border-yellow-200",
  Member: "bg-blue-50 text-blue-700 border-blue-200",
  Guest: "bg-slate-100 text-slate-600 border-slate-200",
};

const STATUS_PILL = {
  "Đang ở": "text-emerald-600 bg-emerald-50",
  "Đã ra về": "text-slate-500 bg-transparent",
  "Chờ xác nhận": "text-amber-600 bg-amber-50",
};

function Stars({ count }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <svg
          key={i}
          viewBox="0 0 12 12"
          className={`h-3.5 w-3.5 ${i < count ? "fill-amber-400" : "fill-slate-200"} `}
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

function formatLastVisit(dateStr) {
  if (!dateStr) return "Chưa từng";
  try {
    const dt = new Date(dateStr.replace(" ", "T"));
    if (isNaN(dt.getTime())) return dateStr;

    const now = new Date();
    const isToday = dt.toDateString() === now.toDateString();

    const yesterday = new Date();
    yesterday.setDate(now.getDate() - 1);
    const isYesterday = dt.toDateString() === yesterday.toDateString();

    const timeStr = dt.toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    if (isToday) return `Hôm nay, ${timeStr} `;
    if (isYesterday) return `Hôm qua, ${timeStr} `;

    return (
      dt.toLocaleDateString("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      }) + `, ${timeStr} `
    );
  } catch {
    return dateStr;
  }
}

export default function CustomersPage() {
  const router = useRouter();
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
    const interval = setInterval(load, 3000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [role]);

  if (role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-slate-500 font-medium">Đang chuyển hướng...</p>
      </div>
    );
  }

  // Map database customers to UI structures
  const mappedCustomers = dbCustomers.map((c) => {
    const isPresent = liveCustomers.some((lc) => lc.id === c.id);
    let status = "Đã ra về";
    if (isPresent) {
      status = "Đang ở";
    } else if (c.id.startsWith("GUEST_")) {
      status = "Chờ xác nhận";
    }

    const rank = rankLabel(c.visit_count);
    const displayId = c.id.startsWith("GUEST_") ? c.id : `CLIENT_${c.id} `;

    return {
      id: c.id,
      displayId,
      name: c.name || "Khách mời",
      visits: c.visit_count || 0,
      rank,
      stars: rank === "VIP" ? 5 : rank === "Member" ? 4 : 3,
      lastVisit: formatLastVisit(c.last_visit),
      status,
    };
  });

  const filtered = mappedCustomers.filter((c) => {
    if (
      query &&
      !c.name.toLowerCase().includes(query.toLowerCase()) &&
      !c.id.toLowerCase().includes(query.toLowerCase())
    )
      return false;
    if (tab === "present") return c.status === "Đang ở";
    if (tab === "pending") return c.status === "Chờ xác nhận";
    if (tab === "vip") return c.rank === "VIP";
    return true;
  });

  const allCount = mappedCustomers.length;
  const presentCount = mappedCustomers.filter(
    (c) => c.status === "Đang ở",
  ).length;
  const pendingCount = mappedCustomers.filter(
    (c) => c.status === "Chờ xác nhận",
  ).length;
  const vipCount = mappedCustomers.filter((c) => c.rank === "VIP").length;

  const tabs = [
    { key: "all", label: "Tất cả", count: allCount },
    { key: "present", label: "Đang ở", count: presentCount },
    { key: "pending", label: "Chờ xác nhận", count: pendingCount },
    { key: "vip", label: "VIP", count: vipCount },
  ];

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="customers" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 bg-slate-50">
          <PageHeader
            title="Quản lý Khách hàng"
            subtitle="Danh sách toàn bộ khách hàng được nhận diện bởi hệ thống."
          />

          <div className="flex flex-1 min-h-0 flex-col p-4 sm:p-5 lg:p-6">
            {/* Search + filter bar */}
            <div className="mb-4 flex shrink-0 items-center gap-3">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Tìm kiếm khách hàng..."
                  className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-4 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-blue-400"
                />
              </div>
              <div className="ml-auto flex items-center gap-2">
                <button className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-600 hover:bg-slate-50">
                  <SlidersHorizontal className="h-4 w-4" />
                  Lọc
                </button>
                <button className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-600 hover:bg-slate-50">
                  Hôm nay
                  <ChevronDown className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Tabs */}
            <div className="mb-5 flex shrink-0 items-center gap-2">
              {tabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`rounded - lg px - 3 py - 1.5 text - sm font - medium transition ${
                    tab === t.key
                      ? "bg-blue-600 text-white"
                      : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  } `}
                >
                  {t.label} {t.count}
                </button>
              ))}
            </div>

            {/* Table */}
            <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-slate-200 bg-white">
              {isLoading ? (
                <div className="px-5 py-8 text-center text-sm text-slate-400">
                  Đang tải danh sách khách hàng...
                </div>
              ) : filtered.length === 0 ? (
                <div className="px-5 py-8 text-center text-sm text-slate-400">
                  Không tìm thấy khách hàng nào.
                </div>
              ) : (
                <table className="w-full min-w-[700px] table-auto text-left">
                  <thead>
                    <tr className="border-b border-slate-100">
                      {[
                        "Khách hàng",
                        "Mã ID",
                        "Hạng",
                        "Lượt ghé",
                        "Lần cuối",
                        "Đánh giá",
                        "Trạng thái",
                      ].map((col) => (
                        <th
                          key={col}
                          className="px-5 py-3.5 text-xs font-medium text-slate-400"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {filtered.map((c) => (
                      <tr key={c.id} className="hover:bg-slate-50/60">
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <div className="h-9 w-9 shrink-0 rounded-full bg-gradient-to-br from-blue-100 to-slate-200" />
                            <Link
                              href={`/ customers / ${c.id} `}
                              className="text-sm font-semibold text-slate-900 hover:text-blue-600"
                            >
                              {c.name}
                            </Link>
                          </div>
                        </td>
                        <td className="px-5 py-4 text-sm text-slate-500">
                          {c.displayId}
                        </td>
                        <td className="px-5 py-4">
                          <span
                            className={`rounded - full border px - 2.5 py - 0.5 text - xs font - medium ${RANK_PILL[c.rank]} `}
                          >
                            {c.rank}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-sm text-slate-700">
                          {c.visits}
                        </td>
                        <td className="px-5 py-4 text-sm text-slate-500">
                          {c.lastVisit}
                        </td>
                        <td className="px-5 py-4">
                          <Stars count={c.stars} />
                        </td>
                        <td className="px-5 py-4">
                          <span
                            className={`rounded - full px - 2.5 py - 1 text - xs font - medium ${STATUS_PILL[c.status]} `}
                          >
                            {c.status}
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
