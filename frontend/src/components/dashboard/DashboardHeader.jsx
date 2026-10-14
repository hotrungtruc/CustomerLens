"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Calendar,
  ChevronDown,
  LayoutDashboard,
  Camera,
  Sun,
  Moon,
  Settings,
  Bell,
  UtensilsCrossed,
} from "lucide-react";
import { useApp } from "../../context/AppContext";

export default function DashboardHeader({
  activeView = "dashboard",
  onViewChange = () => {},
  selectedBranch = "Downtown Branch",
  onBranchChange = () => {},
}) {
  const { lang, theme, toggleLang, toggleTheme, t } = useApp();
  const [currentDateStr, setCurrentDateStr] = useState("");
  const [showBranchMenu, setShowBranchMenu] = useState(false);

  useEffect(() => {
    const now = new Date();
    const formatted = now.toLocaleDateString(lang === "vi" ? "vi-VN" : "en-US", {
      weekday: "long",
      year: "numeric",
      month: "short",
      day: "numeric",
    });
    setCurrentDateStr(formatted);
  }, [lang]);

  const branches = [
    "Downtown Branch",
    "Main Entrance • Cam 01",
    "VIP Lounge & Bar",
    "Rooftop Terrace",
  ];

  return (
    <header className="relative z-30 flex flex-col gap-3 border-b border-slate-200/80 bg-white/90 px-5 py-3.5 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-900/90 lg:flex-row lg:items-center lg:justify-between transition-colors">
      {/* ── Left: Dashboard Title + Branch Selector ── */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-500/20">
            <UtensilsCrossed className="h-4 w-4" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white font-display">
            {t("dashboard_title")}
          </h1>
        </div>

        {/* Branch Selector Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowBranchMenu(!showBranchMenu)}
            className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700/80 bg-slate-50 dark:bg-slate-800/80 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-750 transition-colors"
          >
            <span>{selectedBranch}</span>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          </button>

          {showBranchMenu && (
            <div className="absolute left-0 mt-1.5 w-52 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-1 shadow-xl z-50">
              {branches.map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => {
                    onBranchChange(b);
                    setShowBranchMenu(false);
                  }}
                  className={`flex w-full items-center rounded-lg px-3 py-2 text-left text-xs font-medium transition-colors ${
                    selectedBranch === b
                      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 font-semibold"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                  }`}
                >
                  {b}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Center: View Mode Segmented Control ── */}
      <div className="flex items-center rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800/60 p-1 self-start lg:self-auto">
        <button
          type="button"
          onClick={() => onViewChange("dashboard")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
            activeView === "dashboard"
              ? "bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm"
              : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <LayoutDashboard className="h-3.5 w-3.5" />
          <span>{t("dashboard_overview_toggle")}</span>
        </button>

        <button
          type="button"
          onClick={() => onViewChange("camera")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
            activeView === "camera"
              ? "bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm"
              : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <Camera className="h-3.5 w-3.5" />
          <span>{t("live_stream_toggle")}</span>
        </button>
      </div>

      {/* ── Right: Date, Manager Profile & Controls ── */}
      <div className="flex flex-wrap items-center gap-2.5">
        {/* Date Display */}
        <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 pr-2">
          <Calendar className="h-3.5 w-3.5" />
          <span>{currentDateStr || "Wednesday, Oct 14, 2026"}</span>
        </div>

        {/* Manager User Pill */}
        <div className="flex items-center gap-2 rounded-full border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 pl-1 pr-3 py-1">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=60&h=60&fit=crop&crop=face"
            alt="Manager"
            className="h-6 w-6 rounded-full object-cover ring-1 ring-blue-500/40"
          />
          <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
            Manager
          </span>
          <ChevronDown className="h-3 w-3 text-slate-400" />
        </div>

        {/* Dark/Light Mode Toggle */}
        <button
          type="button"
          onClick={toggleTheme}
          title={theme === "dark" ? t("toggle_theme_light") : t("toggle_theme_dark")}
          className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors shadow-sm"
        >
          {theme === "dark" ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-slate-600" />}
        </button>

        {/* Language Toggle (UK / VN Flag) */}
        <button
          type="button"
          onClick={toggleLang}
          title={lang === "vi" ? t("toggle_lang_en") : t("toggle_lang_vi")}
          className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors shadow-sm overflow-hidden"
        >
          {lang === "vi" ? (
            <svg viewBox="0 0 36 36" className="h-5 w-5 rounded-full">
              <rect fill="#DA251D" width="36" height="36" />
              <polygon fill="#FF0" points="18,7.5 21.2,17.4 31.6,17.4 23.2,23.5 26.4,33.4 18,27.3 9.6,33.4 12.8,23.5 4.4,17.4 14.8,17.4" />
            </svg>
          ) : (
            <svg viewBox="0 0 36 36" className="h-5 w-5 rounded-full">
              <path fill="#012169" d="M0,0 v36 h36 v-36 z" />
              <path fill="#FFF" d="M0,0 L36,36 M36,0 L0,36" stroke="#FFF" strokeWidth="6" />
              <path fill="#C8102E" d="M0,0 L36,36 M36,0 L0,36" stroke="#C8102E" strokeWidth="3" />
              <path fill="#FFF" d="M18,0 v36 M0,18 h36" stroke="#FFF" strokeWidth="10" />
              <path fill="#C8102E" d="M18,0 v36 M0,18 h36" stroke="#C8102E" strokeWidth="6" />
            </svg>
          )}
        </button>

        {/* Notification Bell */}
        <button
          type="button"
          title={t("notifications")}
          className="relative flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors shadow-sm"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full bg-blue-500" />
        </button>

        {/* Settings Link */}
        <Link
          href="/settings"
          title={t("nav_settings")}
          className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors shadow-sm"
        >
          <Settings className="h-4 w-4" />
        </Link>
      </div>
    </header>
  );
}
