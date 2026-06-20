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
  Menu,
  X,
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
    <>
      <aside className="hidden h-full min-h-0 w-16 shrink-0 flex-col items-center border-r border-slate-100 bg-white py-3 lg:flex">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900"
          aria-label="Mở menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <div className="mt-4 flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-xs font-bold text-white">
          FD
        </div>

        <div className="mt-5 flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
          <ActiveIcon className="h-4 w-4" />
        </div>

        <div className="mt-auto flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">
          {getAvatarLetter(username)}
        </div>
      </aside>

      {open ? (
        <div className="fixed inset-0 z-50 hidden lg:block">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/35"
            onClick={() => setOpen(false)}
            aria-label="Đóng menu"
          />

          <div className="absolute bottom-4 left-4 top-4 flex w-72 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-xs font-bold text-white">
                  FD
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-800">
                    Front Desk AI
                  </p>
                  <p className="text-xs text-slate-400">{getRoleBadge(role)}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                aria-label="Đóng menu"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <nav className="flex flex-col gap-1 px-3 py-3">
              {allowedNav.map(({ key, label, href, Icon }) => {
                const isActive = key === active;
                return (
                  <Link
                    key={key}
                    href={href}
                    onClick={() => setOpen(false)}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-blue-600 text-white"
                        : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                    }`}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {label}
                  </Link>
                );
              })}
            </nav>

            <div className="mt-auto border-t border-slate-100 p-3">
              <div className="flex items-center justify-between rounded-lg bg-slate-50 p-2.5">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
                    {getAvatarLetter(username)}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-slate-800">
                      {username}
                    </p>
                    <p className="text-[10px] font-medium text-slate-400">
                      {getRoleBadge(role)}
                    </p>
                  </div>
                </div>

                {role !== "guest" ? (
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700"
                    aria-label="Đăng xuất"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      router.push("/login");
                    }}
                    className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700"
                    aria-label="Đăng nhập"
                  >
                    <LogIn className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
