"use client";

import React from "react";
import { Users2, CheckCircle2, AlertCircle, Clock, MoreHorizontal } from "lucide-react";
import { useApp } from "../../context/AppContext";

const DEFAULT_STAFF = [
  {
    id: "staff_1",
    name: "Sarah Jenkins",
    role: "Manager",
    time: "07:58 AM",
    status: "Verified",
    avatar: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=100&h=100&fit=crop&crop=face",
  },
  {
    id: "staff_2",
    name: "Marcus Vance",
    role: "Head Chef",
    time: "08:15 AM",
    status: "Verified",
    avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=face",
  },
  {
    id: "staff_3",
    name: "Li Wei",
    role: "Server",
    time: "08:45 AM",
    status: "Verified",
    avatar: "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=100&h=100&fit=crop&crop=face",
  },
  {
    id: "staff_4",
    name: "Amanda Smith",
    role: "Host",
    time: "--:--",
    status: "Not Checked In",
    avatar: "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=100&h=100&fit=crop&crop=face",
  },
];

export default function StaffAttendanceCard({ staffList = DEFAULT_STAFF }) {
  const { t } = useApp();

  return (
    <div className="flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-white dark:border-slate-800/80 dark:bg-slate-900/90 p-5 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/80 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-500 dark:bg-indigo-500/15 dark:text-indigo-400">
            <Users2 className="h-4 w-4" />
          </div>
          <h4 className="text-sm font-semibold text-slate-800 dark:text-white">
            {t("staff_face_attendance")}
          </h4>
        </div>

        <button
          type="button"
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      {/* Staff Feed List */}
      <div className="divide-y divide-slate-100 dark:divide-slate-800/60 overflow-hidden">
        {staffList.map((member) => {
          const isVerified = member.status === "Verified";

          return (
            <div
              key={member.id}
              className="flex items-center justify-between py-3.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-850/50 rounded-xl px-2"
            >
              {/* Left: Avatar + Details */}
              <div className="flex items-center gap-3">
                <div className="relative h-11 w-11 shrink-0 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={member.avatar}
                    alt={member.name}
                    className="h-full w-full object-cover"
                  />
                  <span
                    className={`absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-white dark:border-slate-900 ${
                      isVerified ? "bg-emerald-500" : "bg-amber-500"
                    }`}
                  />
                </div>

                <div>
                  <h5 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {member.name}{" "}
                    <span className="text-xs font-normal text-slate-400 dark:text-slate-500">
                      ({member.role})
                    </span>
                  </h5>
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                    <Clock className="h-3 w-3" />
                    <span className="font-mono text-[11px]">{member.time}</span>
                  </div>
                </div>
              </div>

              {/* Right: Verification Status Badge */}
              <div>
                {isVerified ? (
                  <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {t("verified")}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-600 dark:bg-amber-500/15 dark:text-amber-400">
                    <AlertCircle className="h-3.5 w-3.5" />
                    {t("not_checked_in")}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
