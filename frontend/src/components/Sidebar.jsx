"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Camera,
  Users,
  History,
  Bell,
  BarChart2,
  Settings,
  LogIn,
  LogOut,
} from "lucide-react";

const ALL_NAV_ITEMS = [
  { key: "overview", label: "Tổng quan", href: "/", Icon: LayoutDashboard, roles: ["guest", "moderator", "admin"] },
  { key: "camera", label: "Camera", href: "/camera", Icon: Camera, roles: ["moderator", "admin"] },
  { key: "customers", label: "Khách hàng", href: "/customers", Icon: Users, roles: ["admin"] },
  { key: "history", label: "Lịch sử", href: "/history", Icon: History, roles: ["admin"] },
  { key: "notifications", label: "Thông báo", href: "/notifications", Icon: Bell, roles: ["admin"] },
  { key: "reports", label: "Báo cáo", href: "/reports", Icon: BarChart2, roles: ["admin"] },
  { key: "settings", label: "Cài đặt", href: "/settings", Icon: Settings, roles: ["admin"] },
];

export default function Sidebar({ active = "overview" }) {
  const router = useRouter();
  const [role, setRole] = useState("guest");
  const [username, setUsername] = useState("");

  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    const savedUser = localStorage.getItem("username") || "Khách";
    setRole(savedRole);
    setUsername(savedUser);
  }, []);

  const allowedNav = ALL_NAV_ITEMS.filter((item) => item.roles.includes(role));

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("username");
    localStorage.removeItem("cameras");
    router.push("/login");
  };

  const getRoleBadge = (r) => {
    if (r === "admin") return "Admin";
    if (r === "moderator") return "Mod";
    return "Guest";
  };

  const getAvatarLetter = (name) => {
    return (name || "K").charAt(0).toUpperCase();
  };

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
        {allowedNav.map(({ key, label, href, Icon }) => {
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

      {/* Bottom Profile / Login Area */}
      <div className="mt-auto border-t border-slate-50 p-3">
        <div className="flex items-center justify-between rounded-xl bg-slate-50 p-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
              {getAvatarLetter(username)}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-slate-800">{username}</p>
              <p className="text-[10px] text-slate-400 font-medium">{getRoleBadge(role)}</p>
            </div>
          </div>
          {role !== "guest" ? (
            <button
              onClick={handleLogout}
              title="Đăng xuất"
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          ) : (
            <button
              onClick={() => router.push("/login")}
              title="Đăng nhập"
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
            >
              <LogIn className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}