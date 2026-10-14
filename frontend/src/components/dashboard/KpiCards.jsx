"use client";

import React from "react";
import { Users, Crown, ShieldAlert, TrendingUp, AlertTriangle } from "lucide-react";
import { useApp } from "../../context/AppContext";

export default function KpiCards({ reportsData = null, vipCount = 12, footTraffic = 1245, staffVerified = 18, staffTotal = 20 }) {
  const { t } = useApp();

  const traffic = reportsData?.total_visits || footTraffic;
  const vips = reportsData?.vip_visits || vipCount;
  const repeatRate = reportsData?.repeat_rate || 74.2;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {/* ── Card 1: Today's Foot Traffic ── */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white dark:border-slate-800/80 dark:bg-slate-900/90 p-5 shadow-sm transition-all hover:border-slate-300 dark:hover:border-slate-700 hover:shadow-md">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-500 dark:bg-cyan-500/15 dark:text-cyan-400">
              <Users className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {t("today_foot_traffic")}
              </p>
              <h3 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white font-display">
                {traffic.toLocaleString()}
              </h3>
            </div>
          </div>
          <div className="flex items-center text-xs font-semibold text-emerald-500 dark:text-emerald-400">
            <TrendingUp className="mr-1 h-3.5 w-3.5" />
            <span>+12.4%</span>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-slate-100 dark:border-slate-800/70 pt-3 text-xs">
          <span className="text-emerald-600 dark:text-emerald-400 font-medium">
            ↑ +12.4% <span className="text-slate-400 dark:text-slate-500 font-normal">{t("vs_last_week")}</span>
          </span>
          <span className="text-[11px] font-mono text-slate-400 dark:text-slate-500">
            {repeatRate}% {t("returning_guests")}
          </span>
        </div>
      </div>

      {/* ── Card 2: VIP Checked-In ── */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white dark:border-slate-800/80 dark:bg-slate-900/90 p-5 shadow-sm transition-all hover:border-slate-300 dark:hover:border-slate-700 hover:shadow-md">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-500/10 text-blue-500 dark:bg-blue-500/15 dark:text-blue-400">
              <Crown className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {t("vip_checked_in")}
              </p>
              <h3 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white font-display">
                {vips} {t("guest")}s
              </h3>
            </div>
          </div>
          <span className="flex h-6 items-center rounded-full bg-blue-50 px-2.5 text-[10px] font-semibold text-blue-600 dark:bg-blue-950/60 dark:text-blue-300">
            VIP Tier
          </span>
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-slate-100 dark:border-slate-800/70 pt-3 text-xs">
          <span className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-slate-300">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>4 {t("active_now")}</span>
          </span>
          <span className="text-[11px] text-slate-400 dark:text-slate-500">
            Front-door HUD
          </span>
        </div>
      </div>

      {/* ── Card 3: Staff On Duty ── */}
      <div className="relative overflow-hidden rounded-2xl border border-amber-200/70 bg-white dark:border-amber-500/20 dark:bg-slate-900/90 p-5 shadow-sm transition-all hover:border-amber-300 dark:hover:border-amber-500/30 hover:shadow-md sm:col-span-2 lg:col-span-1">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-500/10 text-amber-500 dark:bg-amber-500/15 dark:text-amber-400">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {t("staff_on_duty")}
              </p>
              <h3 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white font-display">
                {staffVerified} / {staffTotal}
              </h3>
            </div>
          </div>
          <span className="flex h-6 items-center rounded-full bg-amber-50 px-2.5 text-[10px] font-semibold text-amber-600 dark:bg-amber-950/60 dark:text-amber-300">
            Shift Active
          </span>
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-slate-100 dark:border-slate-800/70 pt-3 text-xs">
          <span className="flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>2 {t("absent_late")}</span>
          </span>
          <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
            90% Shift Presence
          </span>
        </div>
      </div>
    </div>
  );
}
