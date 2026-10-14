"use client";

import React from "react";
import { Star, Clock, MoreHorizontal, ChevronRight, Crown } from "lucide-react";
import { useApp } from "../../context/AppContext";

const DEFAULT_VIP_CHECKINS = [
  {
    id: "003",
    name: "Johnathan Miller",
    time: "11:15 AM",
    tier: "VIP Gold",
    tierStyle: "bg-amber-500/15 text-amber-500 border-amber-500/30",
    visits: 42,
    avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&h=100&fit=crop&crop=face",
  },
  {
    id: "002",
    name: "Elena Rostova",
    time: "10:52 AM",
    tier: "VIP Silver",
    tierStyle: "bg-slate-400/15 text-slate-300 border-slate-400/30",
    visits: 28,
    avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&h=100&fit=crop&crop=face",
  },
  {
    id: "001",
    name: "David Chen",
    time: "10:30 AM",
    tier: "Regular 25+ visits",
    tierStyle: "bg-blue-500/15 text-blue-400 border-blue-500/30",
    visits: 25,
    avatar: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100&h=100&fit=crop&crop=face",
  },
  {
    id: "LN8",
    name: "Ho Trung Truc",
    time: "10:15 AM",
    tier: "VIP Diamond",
    tierStyle: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
    visits: 68,
    avatar: null,
  },
];

export default function RealtimeVipFeed({ liveVipList = [], onSelectCustomer = null }) {
  const { t } = useApp();

  // Merge live WebSocket recognized customers with defaults if live is small
  const items = (liveVipList && liveVipList.length > 0)
    ? liveVipList.map((c, i) => {
        const timeStr = c.detected_at
          ? new Date(c.detected_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
          : DEFAULT_VIP_CHECKINS[i % DEFAULT_VIP_CHECKINS.length].time;

        const isVip = c.total_visits >= 30 || c.loyalty_tier === "VIP";
        const tierName = isVip ? "VIP Gold" : c.total_visits >= 10 ? "VIP Silver" : "Member";
        const tierStyle = isVip
          ? "bg-amber-500/15 text-amber-500 border-amber-500/30"
          : "bg-blue-500/15 text-blue-400 border-blue-500/30";

        return {
          id: c.id,
          name: c.name || `Client #${c.id}`,
          time: timeStr,
          tier: tierName,
          tierStyle: tierStyle,
          visits: c.total_visits || 1,
          avatar: c.faceImage || null,
        };
      })
    : DEFAULT_VIP_CHECKINS;

  return (
    <div className="flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-white dark:border-slate-800/80 dark:bg-slate-900/90 p-5 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/80 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10 text-blue-500 dark:bg-blue-500/15 dark:text-blue-400">
            <Star className="h-4 w-4 fill-current" />
          </div>
          <h4 className="text-sm font-semibold text-slate-800 dark:text-white">
            {t("realtime_vip_checkin")}
          </h4>
        </div>

        <button
          type="button"
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      {/* Guest Feed List */}
      <div className="divide-y divide-slate-100 dark:divide-slate-800/60 overflow-hidden">
        {items.slice(0, 4).map((guest, idx) => (
          <div
            key={guest.id || idx}
            onClick={() => onSelectCustomer?.(guest)}
            className="group flex items-center justify-between py-3.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-850/50 cursor-pointer rounded-xl px-2"
          >
            {/* Left: Avatar + Details */}
            <div className="flex items-center gap-3">
              <div className="relative h-11 w-11 shrink-0 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800">
                {guest.avatar ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img
                    src={guest.avatar}
                    alt={guest.name}
                    className="h-full w-full object-cover transition-transform group-hover:scale-105"
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center font-bold text-slate-600 dark:text-slate-300">
                    {guest.name.charAt(0)}
                  </div>
                )}
                {/* Status indicator */}
                <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-white dark:border-slate-900 bg-emerald-500" />
              </div>

              <div>
                <h5 className="text-sm font-semibold text-slate-800 dark:text-slate-100 group-hover:text-blue-500 transition-colors">
                  {guest.name}
                </h5>
                <div className="flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                  <Clock className="h-3 w-3" />
                  <span className="font-mono text-[11px]">{guest.time}</span>
                  <span className="text-[10px] text-slate-300 dark:text-slate-600">•</span>
                  <span className="text-[11px]">{guest.visits} visits</span>
                </div>
              </div>
            </div>

            {/* Right: Membership Tier Badge */}
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-semibold ${guest.tierStyle}`}
              >
                <Crown className="h-3 w-3" />
                {guest.tier}
              </span>
              <ChevronRight className="h-4 w-4 text-slate-400 opacity-0 transition-opacity group-hover:opacity-100" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
