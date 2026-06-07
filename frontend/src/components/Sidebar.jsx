"use client";

import Link from "next/link";
import {
  LayoutDashboard,
  Camera,
  Users,
  History,
  Bell,
  BarChart2,
  Settings,
} from "lucide-react";

const NAV_ITEMS = [
  { key: "overview", label: "Tổng quan", href: "/", Icon: LayoutDashboard },
  { key: "camera", label: "Camera", href: "/camera", Icon: Camera },
  { key: "customers", label: "Khách hàng", href: "/customers", Icon: Users },
  { key: "history", label: "Lịch sử", href: "/history", Icon: History },
  { key: "notifications", label: "Thông báo", href: "/notifications", Icon: Bell },
  { key: "reports", label: "Báo cáo", href: "/reports", Icon: BarChart2 },
  { key: "settings", label: "Cài đặt", href: "/settings", Icon: Settings },
];

export default function Sidebar({ active = "overview" }) {
  return (
    <aside className="hidden w-[220px] shrink-0 flex-col border-r border-slate-100 bg-white lg:flex">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-sm font-bold text-white">
          FD
        </div>
        <span className="text-[15px] font-semibold text-slate-800">Front Desk AI</span>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-0.5 px-3 pt-2">
        {NAV_ITEMS.map(({ key, label, href, Icon }) => {
          const isActive = key === active;
          return (
            <Link
              key={key}
              href={href}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${isActive
                  ? "bg-blue-600 text-white"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-800"
                }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Admin */}
      <div className="mt-auto px-3 pb-5">
        <div className="flex items-center gap-3 rounded-xl px-3 py-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
            A
          </div>
          <span className="text-sm font-medium text-slate-700">Admin</span>
        </div>
      </div>
    </aside>
  );
}