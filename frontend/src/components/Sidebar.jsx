"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Camera,
  Users,
  History,
  Shield,
  Settings,
  LogIn,
  LogOut,
} from "lucide-react";
import { useApp } from "../context/AppContext";

const ALL_NAV_ITEMS = [
  {
    key: "overview",
    transKey: "nav_overview",
    label: "Overview",
    href: "/",
    Icon: LayoutDashboard,
    roles: ["guest", "moderator", "admin"],
  },
  {
    key: "camera",
    transKey: "nav_camera",
    label: "Camera",
    href: "/camera",
    Icon: Camera,
    roles: ["moderator", "admin"],
  },
  {
    key: "customers",
    transKey: "nav_customers",
    label: "Customers",
    href: "/customers",
    Icon: Users,
    roles: ["admin"],
  },
  {
    key: "history",
    transKey: "nav_history",
    label: "History",
    href: "/history",
    Icon: History,
    roles: ["admin"],
  },
  {
    key: "notifications",
    transKey: "nav_authorization",
    label: "Authorization",
    href: "/authorization",
    Icon: Shield,
    roles: ["admin"],
  },
  {
    key: "settings",
    transKey: "nav_settings",
    label: "Settings",
    href: "/settings",
    Icon: Settings,
    roles: ["admin"],
  },
];

export default function Sidebar({ active = "overview" }) {
  const router = useRouter();
  const { t } = useApp();
  const [role, setRole] = useState("guest");
  const [username, setUsername] = useState("");

  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    const savedUser = localStorage.getItem("username") || "Guest";
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

  const getRoleBadge = (value) => {
    if (value === "admin") return "Admin";
    if (value === "moderator") return "Mod";
    return t("guest") || "Guest";
  };

  const getAvatarLetter = (name) => (name || "G").charAt(0).toUpperCase();

  return (
    <div className="relative z-50 hidden h-full w-16 lg:block shrink-0">
      <aside className="group absolute inset-y-0 left-0 flex w-16 flex-col overflow-hidden border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-[width] duration-300 ease-in-out hover:w-64 hover:shadow-2xl">
        {/* Logo Area */}
        <div className="flex h-20 shrink-0 items-center px-3">
          <Link
            href="/"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl overflow-hidden transition-transform hover:scale-105"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo_small.png"
              alt="CustomerLens"
              className="h-10 w-10 object-contain drop-shadow"
            />
          </Link>
          <div className="ml-3 flex flex-col whitespace-nowrap opacity-0 transition-opacity duration-300 group-hover:opacity-100 delay-75">
            <span className="text-sm font-bold text-slate-900 dark:text-white">CustomerLens</span>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {getRoleBadge(role)}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden px-3 py-4">
          {allowedNav.map(({ key, transKey, label, href, Icon }) => {
            const isActive = key === active;
            return (
              <Link
                key={key}
                href={href}
                className={`relative flex h-10 w-full shrink-0 items-center rounded-xl transition-colors ${
                  isActive
                    ? "bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-400"
                    : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {isActive && (
                  <span className="absolute -left-3 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-blue-600" />
                )}
                <div className="flex h-10 w-10 shrink-0 items-center justify-center">
                  <Icon className={`h-5 w-5 ${isActive ? "stroke-[2.5px]" : "stroke-2"}`} />
                </div>
                <span className="ml-1 whitespace-nowrap text-sm font-medium opacity-0 transition-opacity duration-300 group-hover:opacity-100 delay-75">
                  {transKey ? t(transKey) : label}
                </span>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="shrink-0 p-3">
          <div className="flex items-center gap-3 rounded-xl border border-transparent p-1 transition-colors group-hover:border-slate-200 dark:group-hover:border-slate-800 group-hover:bg-slate-50 dark:group-hover:bg-slate-800/50">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 dark:bg-slate-700 text-xs font-bold text-slate-700 dark:text-slate-200">
              {getAvatarLetter(username)}
            </div>
            <div className="flex flex-1 flex-col overflow-hidden whitespace-nowrap opacity-0 transition-opacity duration-300 group-hover:opacity-100 delay-75">
              <span className="truncate text-sm font-semibold text-slate-900 dark:text-white">
                {username}
              </span>
              <span className="truncate text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                {role === "admin" ? "Administrator" : "Guest Account"}
              </span>
            </div>
            
            <div className="opacity-0 transition-opacity duration-300 group-hover:opacity-100 delay-75">
              {role !== "guest" ? (
                <button
                  onClick={handleLogout}
                  title={t("logout_btn")}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-rose-100 dark:hover:bg-rose-950/60 hover:text-rose-600 dark:hover:text-rose-400 transition-colors"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              ) : (
                <button
                  onClick={() => router.push("/login")}
                  title={t("login_btn")}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-blue-100 dark:hover:bg-blue-950/60 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
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
