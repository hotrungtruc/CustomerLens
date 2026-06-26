"use client";

import { useState } from "react";
import Link from "next/link";
import {
  LayoutDashboard,
  Camera,
  Users,
  History,
  Shield,
  BarChart2,
  Settings,
  X,
  Menu,
} from "lucide-react";

const ITEMS = [
  { href: "/", label: "Tổng quan", Icon: LayoutDashboard },
  { href: "/camera", label: "Camera", Icon: Camera },
  { href: "/customers", label: "Khách hàng", Icon: Users },
  { href: "/history", label: "Lịch sử", Icon: History },
  { href: "/notifications", label: "Phân quyền", Icon: Shield },
  { href: "/reports", label: "Báo cáo", Icon: BarChart2 },
  { href: "/settings", label: "Cài đặt", Icon: Settings },
];

export default function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <div className="lg:hidden">
      <div className="fixed inset-x-0 top-0 z-50 flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-xs font-bold text-white">
            FD
          </div>
          <span className="text-sm font-semibold text-slate-800">
            Front Desk AI
          </span>
        </div>
        <button
          onClick={() => setOpen(true)}
          className="rounded-lg border border-slate-200 p-2 text-slate-500"
        >
          <Menu className="h-4 w-4" />
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-40 flex">
          <div className="w-60 border-r border-slate-100 bg-white px-3 py-5">
            <div className="mb-5 flex items-center justify-between px-2">
              <span className="text-sm font-semibold text-slate-800">Menu</span>
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-50"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav className="flex flex-col gap-1">
              {ITEMS.map(({ href, label, Icon }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex-1 bg-black/20" onClick={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}
