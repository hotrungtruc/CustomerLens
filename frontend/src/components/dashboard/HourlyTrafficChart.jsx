"use client";

import React, { useState } from "react";
import { Activity, MoreHorizontal } from "lucide-react";
import { useApp } from "../../context/AppContext";

const DEFAULT_HOURLY = [
  { hour: "8 AM", count: 15 },
  { hour: "9 AM", count: 48 },
  { hour: "10 AM", count: 72 },
  { hour: "11 AM", count: 96 },
  { hour: "12 PM", count: 165, isPeak: true, peakLabel: "Lunch\n12 PM" },
  { hour: "1 PM", count: 110 },
  { hour: "2 PM", count: 85 },
  { hour: "3 PM", count: 92 },
  { hour: "4 PM", count: 108 },
  { hour: "5 PM", count: 112 },
  { hour: "6 PM", count: 125 },
  { hour: "7 PM", count: 155, isPeak: true, peakLabel: "Dinner\n7 PM" },
  { hour: "8 PM", count: 118 },
  { hour: "9 PM", count: 82 },
  { hour: "10 PM", count: 38 },
];

export default function HourlyTrafficChart({ hourlyData = null }) {
  const { t } = useApp();
  const [hoveredIndex, setHoveredIndex] = useState(null);

  const data = (hourlyData && hourlyData.length >= 8 ? hourlyData : DEFAULT_HOURLY).map((d, idx) => ({
    hour: d.hour,
    count: d.count,
    isPeak: d.isPeak ?? (idx === 4 || idx === 11),
    peakLabel: idx === 4 ? `${t("lunch")}\n12 PM` : idx === 11 ? `${t("dinner")}\n7 PM` : (d.peakLabel || ""),
  }));

  // SVG Chart Geometry
  const W = 700;
  const H = 240;
  const PAD = { top: 45, right: 30, bottom: 40, left: 45 };
  const iW = W - PAD.left - PAD.right;
  const iH = H - PAD.top - PAD.bottom;
  const maxY = 200;

  const points = data.map((d, i) => {
    const x = PAD.left + (i / (data.length - 1)) * iW;
    const y = PAD.top + iH - (Math.min(d.count, maxY) / maxY) * iH;
    return { ...d, x, y };
  });

  // Generate smooth cubic bezier spline curve
  const pathD = points
    .map((p, i) => {
      if (i === 0) return `M ${p.x} ${p.y}`;
      const prev = points[i - 1];
      const mx = (prev.x + p.x) / 2;
      return `C ${mx} ${prev.y}, ${mx} ${p.y}, ${p.x} ${p.y}`;
    })
    .join(" ");

  const areaD = `${pathD} L ${points[points.length - 1].x} ${PAD.top + iH} L ${points[0].x} ${PAD.top + iH} Z`;

  // Grid levels: 200, 150, 100, 50, 0
  const yTicks = [200, 150, 100, 50, 0];

  return (
    <div className="relative flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-white dark:border-slate-800/80 dark:bg-slate-900/90 p-5 shadow-sm">
      {/* Header */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-500 dark:bg-cyan-500/15 dark:text-cyan-400">
            <Activity className="h-4 w-4" />
          </div>
          <h4 className="text-sm font-semibold text-slate-800 dark:text-white">
            {t("hourly_foot_traffic")}
          </h4>
        </div>

        <div className="flex items-center gap-2">
          <span className="hidden sm:inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:text-slate-300">
            {t("today_realtime")}
          </span>
          <button
            type="button"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* SVG Line / Area Graph */}
      <div className="relative w-full overflow-hidden">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full select-none font-sans"
        >
          <defs>
            {/* Smooth glowing gradient fill */}
            <linearGradient id="cyanTrafficGlow" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.38" />
              <stop offset="50%" stopColor="#06b6d4" stopOpacity="0.12" />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.0" />
            </linearGradient>

            {/* Glowing drop shadow filter */}
            <filter id="glowCyan" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Horizontal Grid lines */}
          {yTicks.map((val) => {
            const y = PAD.top + iH - (val / maxY) * iH;
            return (
              <g key={val} className="transition-opacity">
                <line
                  x1={PAD.left}
                  y1={y}
                  x2={W - PAD.right}
                  y2={y}
                  stroke="currentColor"
                  className="text-slate-100 dark:text-slate-800/80"
                  strokeWidth="1"
                  strokeDasharray={val === 0 ? "none" : "3 3"}
                />
                <text
                  x={PAD.left - 10}
                  y={y + 3.5}
                  textAnchor="end"
                  className="fill-slate-400 text-[10px] font-mono dark:fill-slate-500"
                >
                  {val}
                </text>
              </g>
            );
          })}

          {/* Area Fill */}
          <path d={areaD} fill="url(#cyanTrafficGlow)" />

          {/* Spline Path */}
          <path
            d={pathD}
            fill="none"
            stroke="#06b6d4"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#glowCyan)"
          />

          {/* Peak Indicators (Lunch 12 PM & Dinner 7 PM) */}
          {points.map((p, i) => {
            if (!p.isPeak) return null;
            return (
              <g key={`peak-${i}`}>
                {/* Vertical dashed indicator */}
                <line
                  x1={p.x}
                  y1={p.y}
                  x2={p.x}
                  y2={PAD.top + iH}
                  stroke="#06b6d4"
                  strokeWidth="1.2"
                  strokeDasharray="3 3"
                  opacity="0.8"
                />

                {/* Outer halo */}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r="6"
                  fill="#06b6d4"
                  opacity="0.25"
                  className="animate-ping"
                />

                {/* Inner glowing dot */}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r="3.5"
                  fill="#ffffff"
                  stroke="#06b6d4"
                  strokeWidth="2.5"
                />

                {/* Peak Label Pill */}
                <g transform={`translate(${p.x}, ${p.y - 24})`}>
                  <rect
                    x="-32"
                    y="-12"
                    width="64"
                    height="20"
                    rx="10"
                    className="fill-slate-900/90 dark:fill-slate-950/90 stroke-cyan-500/40"
                    strokeWidth="1"
                  />
                  <text
                    x="0"
                    y="2"
                    textAnchor="middle"
                    className="fill-cyan-400 text-[9px] font-semibold tracking-wide"
                  >
                    {p.hour === "12 PM" ? "Lunch 12PM" : "Dinner 7PM"}
                  </text>
                </g>
              </g>
            );
          })}

          {/* Data Points (interactive) */}
          {points.map((p, i) => (
            <g
              key={i}
              className="cursor-pointer"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <circle
                cx={p.x}
                cy={p.y}
                r={hoveredIndex === i ? "5" : "3"}
                fill={hoveredIndex === i ? "#06b6d4" : "transparent"}
                stroke={hoveredIndex === i ? "#ffffff" : "transparent"}
                strokeWidth="2"
              />
            </g>
          ))}

          {/* X-Axis Labels */}
          {points.map((p, i) => {
            // Render every 2 hours or peaks on small viewports
            const showLabel = i % 2 === 0 || p.isPeak;
            if (!showLabel) return null;
            return (
              <text
                key={`x-${i}`}
                x={p.x}
                y={PAD.top + iH + 20}
                textAnchor="middle"
                className="fill-slate-400 text-[10px] font-medium dark:fill-slate-500 font-mono"
              >
                {p.hour}
              </text>
            );
          })}
        </svg>

        {/* Hover Tooltip Overlay */}
        {hoveredIndex !== null && (
          <div
            className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-full rounded-lg border border-slate-700 bg-slate-900/95 px-2.5 py-1 text-center shadow-xl backdrop-blur-md"
            style={{
              left: `${(points[hoveredIndex].x / W) * 100}%`,
              top: `${(points[hoveredIndex].y / H) * 100 - 8}%`,
            }}
          >
            <p className="text-[10px] font-mono text-slate-400">
              {points[hoveredIndex].hour}
            </p>
            <p className="text-xs font-bold text-cyan-400">
              {points[hoveredIndex].count} visits
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
