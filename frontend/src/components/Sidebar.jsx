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
  {
    key: "overview",
    label: "Tổng quan",
    href: "/",
    Icon: LayoutDashboard,
    roles: ["guest", "moderator", "admin"],
  },
  {
    key: "camera",
    label: "Camera",
    href: "/camera",
    Icon: Camera,
    roles: ["moderator", "admin"],
  },
  {
    key: "customers",
    label: "Khách hàng",
    href: "/customers",
    Icon: Users,
    roles: ["admin"],
  },
  {
    key: "history",
    label: "Lịch sử",
    href: "/history",
    Icon: History,
    roles: ["admin"],
  },
  {
    key: "notifications",
    label: "Thông báo",
    href: "/notifications",
    Icon: Bell,
    roles: ["admin"],
  },
  {
    key: "reports",
    label: "Báo cáo",
    href: "/reports",
    Icon: BarChart2,
    roles: ["admin"],
  },
  {
    key: "settings",
    label: "Cài đặt",
    href: "/settings",
    Icon: Settings,
    roles: ["admin"],
  },
];

export default function Sidebar({ active = "overview" }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState("guest");
  const [username, setUsername] = useState("");

  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    const savedUser = localStorage.getItem("username") || "Khách";
    setRole(savedRole);
    setUsername(savedUser);
  }, []);

  const allowedNav = ALL_NAV_ITEMS.filter((item) => item.roles.includes(role));
  const activeItem =
    allowedNav.find((item) => item.key === active) || allowedNav[0];
  const ActiveIcon = activeItem?.Icon || LayoutDashboard;

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("username");
    localStorage.removeItem("cameras");
    setOpen(false);
    router.push("/login");
  };

  const getRoleBadge = (value) => {
    if (value === "admin") return "Admin";
    if (value === "moderator") return "Mod";
    return "Guest";
  };

  const getAvatarLetter = (name) => (name || "K").charAt(0).toUpperCase();

  return (
    <div className="relative z-50 hidden h-full w-16 lg:block shrink-0">
      <aside className="group absolute inset-y-0 left-0 flex w-16 flex-col overflow-hidden border-r border-slate-200 bg-white transition-[width] duration-300 ease-in-out hover:w-64 hover:shadow-2xl">
        {/* Logo Area */}
        <div className="flex h-20 shrink-0 items-center px-3">
          <Link
            href="/"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-sm font-bold text-white shadow-lg shadow-blue-500/30 transition-transform hover:scale-105"
          >
            FD
          </Link>
          <div className="ml-3 flex flex-col whitespace-nowrap opacity-0 transition-opacity duration-300 group-hover:opacity-100 delay-75">
            <span className="text-sm font-bold text-slate-900">Front Desk AI</span>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              {getRoleBadge(role)}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden px-3 py-4">
          {allowedNav.map(({ key, label, href, Icon }) => {
            const isActive = key === active;
            return (
              <Link
                key={key}
                href={href}
                className={`relative flex h-10 w-full shrink-0 items-center rounded-xl transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700"
                    : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                {isActive && (
                  <span className="absolute -left-3 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-blue-600" />
                )}
                <div className="flex h-10 w-10 shrink-0 items-center justify-center">
                  <Icon className={`h-5 w-5 ${isActive ? "stroke-[2.5px]" : "stroke-2"}`} />
                </div>
                <span className="ml-1 whitespace-nowrap text-sm font-medium opacity-0 transition-opacity duration-300 group-hover:opacity-100 delay-75">
                  {label}
                </span>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="shrink-0 p-3">
          <div className="flex items-center gap-3 rounded-xl border border-transparent p-1 transition-colors group-hover:border-slate-200 group-hover:bg-slate-50">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-xs font-bold text-slate-700">
              {getAvatarLetter(username)}
            </div>
            <div className="flex flex-1 flex-col overflow-hidden whitespace-nowrap opacity-0 transition-opacity duration-300 group-hover:opacity-100 delay-75">
              <span className="truncate text-sm font-semibold text-slate-900">
                {username}
              </span>
              <span className="truncate text-[10px] text-slate-500 uppercase tracking-wide">
                {role === "admin" ? "Administrator" : "Guest Account"}
              </span>
            </div>
            
            <div className="opacity-0 transition-opacity duration-300 group-hover:opacity-100 delay-75">
              {role !== "guest" ? (
                <button
                  onClick={handleLogout}
                  title="Đăng xuất"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-rose-100 hover:text-rose-600 transition-colors"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              ) : (
                <button
                  onClick={() => router.push("/login")}
                  title="Đăng nhập"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-blue-100 hover:text-blue-600 transition-colors"
                >
                  <LogIn className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
