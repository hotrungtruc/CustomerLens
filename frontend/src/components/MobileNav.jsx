"use client";

import { useState } from "react";
import Link from "next/link";
import {
  LayoutDashboard,
  Camera,
  Users,
  History,
  Shield,
  Settings,
  X,
  Menu,
} from "lucide-react";
import { useApp } from "../context/AppContext";

const ITEMS = [
  { href: "/", transKey: "nav_overview", defaultLabel: "Overview", Icon: LayoutDashboard },
  { href: "/camera", transKey: "nav_camera", defaultLabel: "Camera", Icon: Camera },
  { href: "/customers", transKey: "nav_customers", defaultLabel: "Customers", Icon: Users },
  { href: "/history", transKey: "nav_history", defaultLabel: "History", Icon: History },
  { href: "/authorization", transKey: "nav_authorization", defaultLabel: "Authorization", Icon: Shield },
  { href: "/settings", transKey: "nav_settings", defaultLabel: "Settings", Icon: Settings },
];

export default function MobileNav() {
  const [open, setOpen] = useState(false);
  const { t } = useApp();

  return (
    <div className="lg:hidden">
      <div className="fixed inset-x-0 top-0 z-50 flex items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <Link href="/" className="flex h-8 w-8 items-center justify-center rounded-lg overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo_small.png"
              alt="CustomerLens"
              className="h-8 w-8 object-contain"
            />
          </Link>
          <span className="text-sm font-semibold text-slate-800 dark:text-white">
            CustomerLens
          </span>
        </div>
        <button
          onClick={() => setOpen(true)}
          className="rounded-lg border border-slate-200 dark:border-slate-700 p-2 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
        >
          <Menu className="h-4 w-4" />
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-40 flex">
          <div className="w-60 border-r border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-5 shadow-2xl">
            <div className="mb-5 flex items-center justify-between px-2">
              <span className="text-sm font-semibold text-slate-800 dark:text-white">Menu</span>
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav className="flex flex-col gap-1">
              {ITEMS.map(({ href, transKey, defaultLabel, Icon }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white transition-colors"
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {t(transKey) || defaultLabel}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex-1 bg-black/40 backdrop-blur-sm" onClick={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}
