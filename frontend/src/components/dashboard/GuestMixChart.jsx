"use client";

import React from "react";
import { PieChart, MoreHorizontal } from "lucide-react";
import { useApp } from "../../context/AppContext";

export default function GuestMixChart({ returningRate = 74.2, newRate = 25.8 }) {
  const { t } = useApp();

  const radius = 62;
  const strokeWidth = 24;
  const circumference = 2 * Math.PI * radius; // ~389.55

  const returningPct = Math.max(0, Math.min(100, returningRate));
  const newPct = Math.max(0, 100 - returningPct);

  // Stroke dash calculations with subtle gap
  const returningDash = (returningPct / 100) * circumference;
  const newDash = (newPct / 100) * circumference;

  return (
    <div className="relative flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-white dark:border-slate-800/80 dark:bg-slate-900/90 p-5 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/10 text-teal-500 dark:bg-teal-500/15 dark:text-teal-400">
            <PieChart className="h-4 w-4" />
          </div>
          <h4 className="text-sm font-semibold text-slate-800 dark:text-white">
            {t("guest_mix")}
          </h4>
        </div>

        <button
          type="button"
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      {/* Donut & Legend Container */}
      <div className="my-auto flex flex-col items-center justify-around gap-6 py-4 sm:flex-row">
        {/* SVG Donut */}
        <div className="relative flex items-center justify-center">
          <svg width="170" height="170" viewBox="0 0 170 170" className="-rotate-90 select-none">
            {/* Background ring */}
            <circle
              cx="85"
              cy="85"
              r={radius}
              fill="transparent"
              stroke="currentColor"
              className="text-slate-100 dark:text-slate-800/60"
              strokeWidth={strokeWidth}
            />

            {/* Segment 1: Returning Guests (Teal/Cyan) */}
            <circle
              cx="85"
              cy="85"
              r={radius}
              fill="transparent"
              stroke="#06b6d4"
              strokeWidth={strokeWidth}
              strokeDasharray={`${returningDash} ${circumference}`}
              strokeDashoffset="0"
              className="transition-all duration-1000 ease-out"
            />

            {/* Segment 2: New Guests (Amber/Gold) */}
            <circle
              cx="85"
              cy="85"
              r={radius}
              fill="transparent"
              stroke="#f59e0b"
              strokeWidth={strokeWidth}
              strokeDasharray={`${newDash} ${circumference}`}
              strokeDashoffset={-returningDash}
              className="transition-all duration-1000 ease-out"
            />
          </svg>

          {/* Center Callout Metric */}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-xl font-bold tracking-tight text-slate-900 dark:text-white font-display">
              {returningPct}%
            </span>
            <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400 dark:text-slate-500">
              Returning
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-col gap-3 min-w-[140px]">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-cyan-500 shadow-sm shadow-cyan-500/30" />
              <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                {t("returning_guests")}
              </span>
            </div>
            <span className="text-xs font-bold text-slate-900 dark:text-white font-mono">
              {returningPct}%
            </span>
          </div>

          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-amber-500 shadow-sm shadow-amber-500/30" />
              <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                {t("new_guests")}
              </span>
            </div>
            <span className="text-xs font-bold text-slate-900 dark:text-white font-mono">
              {newPct.toFixed(1)}%
            </span>
          </div>

          <div className="mt-1 border-t border-slate-100 dark:border-slate-800/80 pt-2 text-[11px] text-slate-400 dark:text-slate-500">
            LTV Retention: <span className="font-semibold text-emerald-500">High (Tier A)</span>
          </div>
        </div>
      </div>
    </div>
  );
}
