"use client";

import { useEffect, useState } from "react";
import { Bell } from "lucide-react";

export default function PageHeader({ title, subtitle }) {
  const [mounted, setMounted] = useState(false);
  const [now, setNow] = useState(null);

  useEffect(() => {
    setMounted(true);
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const days = ["Chủ nhật", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"];

  const dayLabel = mounted && now ? days[now.getDay()] : "";
  const dateLabel = mounted && now
    ? now.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })
    : "";
  const timeLabel = mounted && now
    ? now.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
    : "";

  return (
    <div className="flex items-start justify-between border-b border-slate-100 px-8 py-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-4 pt-1">
        <span className="text-sm text-slate-500 min-w-[160px] text-right">
          {dayLabel}{dayLabel && ", "}{dateLabel}
        </span>
        <span className="text-sm font-medium text-slate-700 min-w-[70px] text-right">
          {timeLabel}
        </span>
        <button
          type="button"
          className="relative inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-blue-500" />
        </button>
      </div>
    </div>
  );
}