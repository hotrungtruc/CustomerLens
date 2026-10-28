"use client";

import React from "react";
import {
  formatCustomerDisplayId,
  getCustomerDisplayName,
  getCustomerSegment,
  getLocalizedSegment,
} from "../lib/customerCode";

import { useApp } from "../context/AppContext";

/**
 * HudCard — Real-time Biometric Customer Intelligence Display.
 * Shows live customer info on hover. Click the bbox to edit/add profile.
 */
export default function HudCard({
  customer,
  face,
  direction = "right",
  verticalAlign = "top",
  onMouseEnter,
  onMouseLeave,
}) {
  const { t, lang } = useApp();

  const isIdentified = Boolean(
    customer &&
      customer.detected &&
      customer.customer_type !== "guest" &&
      customer.name &&
      customer.name.trim() !== "" &&
      customer.name !== "Guest" &&
      customer.name !== "Khách mới" &&
      customer.name !== "New Guest"
  );

  const segment = getLocalizedSegment(getCustomerSegment(customer), lang);
  const displayId = formatCustomerDisplayId(customer, face);
  const isResolved = Boolean(displayId && segment);
  const displayName = isResolved
    ? getCustomerDisplayName(customer, face, lang).toUpperCase()
    : t("identifying");

  const phone = customer?.phone || t("not_provided");
  const email = customer?.email || t("not_provided");
  const visits = customer?.total_visits ?? (isIdentified ? 1 : 0);
  const spending = customer?.total_spending
    ? new Intl.NumberFormat(lang === "vi" ? "vi-VN" : "en-US", {
        style: "currency",
        currency: lang === "vi" ? "VND" : "USD",
      }).format(customer.total_spending)
    : isIdentified
    ? lang === "vi" ? "0 ₫" : "$0"
    : "N/A";

  const note =
    customer?.note ||
    (!isResolved
      ? t("collecting_frames_note")
      : isIdentified
      ? t("verified_profile_note")
      : t("identified_guest_note").replace("%s", displayId));


  return (
    <div
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={`absolute z-50 pointer-events-auto transition-all duration-150 animate-floatIn ${
        direction === "left" ? "right-[calc(100%+8px)]" : "left-[calc(100%+8px)]"
      } ${verticalAlign === "bottom" ? "bottom-0" : "top-0"}`}
      style={{
        width: "310px",
        filter: "drop-shadow(0 0 16px rgba(6, 182, 212, 0.25))",
      }}
    >
      {/* ── Top Header Tab: "DATA" with Chamfered Tech Corner ── */}
      <div className="flex items-end">
        <div
          className="relative px-4 py-1 bg-[#041a1f] border-t border-l border-cyan-400 text-cyan-300 font-mono text-[13px] font-extrabold tracking-widest uppercase flex items-center gap-1.5"
          style={{
            clipPath: "polygon(0 0, calc(100% - 10px) 0, 100% 100%, 0 100%)",
            borderRight: "1px solid rgba(34, 211, 238, 0.6)",
          }}
        >
          <span className="inline-block w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" />
          DATA
        </div>
        <div className="flex-1 h-[1px] bg-cyan-500/40" />
      </div>

      {/* ── Main Panel Body ── */}
      <div
        className="relative bg-[#041417]/95 border border-cyan-500/70 p-4 text-xs font-mono text-cyan-100 shadow-[inset_0_0_20px_rgba(6,182,212,0.12)] backdrop-blur-md"
        style={{
          clipPath:
            "polygon(0 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%)",
        }}
      >
        {/* Subtle Tech Grid Overlay */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.04]"
          style={{
            backgroundImage: "linear-gradient(rgba(34, 211, 238, 1) 1px, transparent 1px)",
            backgroundSize: "100% 3px",
          }}
        />

        {/* 1. SCAN RESULTS (Name in Neon Amber + Clean Short ID + MediaPipe Face Thumbnail) */}
        <div className="mb-3">
          <div className="text-[10px] text-cyan-400/70 font-semibold tracking-wider uppercase mb-1.5 flex items-center justify-between">
            <span>{t("scan_results")}</span>
            {isResolved ? (
              <span className="text-[11px] font-bold px-1.5 py-0.5 rounded border border-cyan-400/60 bg-cyan-950/80 text-cyan-300 tracking-wider">
                ID: #{displayId}
              </span>
            ) : (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-amber-400/60 bg-amber-950/80 text-amber-300 tracking-wider animate-pulse">
                {t("scanning")}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2.5">
            {(face?.faceImage || customer?.faceImage) && (
              <div className="relative w-11 h-11 rounded-lg border border-cyan-400/80 bg-slate-950 overflow-hidden shrink-0 shadow-[0_0_12px_rgba(34,211,238,0.35)]">
                <img
                  src={face?.faceImage || customer?.faceImage}
                  alt="MediaPipe Face"
                  className="w-full h-full object-cover"
                />
                <div className="absolute inset-0 border border-cyan-400/30 pointer-events-none" />
                <div className="absolute bottom-0 right-0 w-2 h-2 bg-cyan-400" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="text-amber-400 font-black text-[15px] tracking-wide leading-tight drop-shadow-[0_0_6px_rgba(245,158,11,0.5)] truncate">
                {displayName}
              </div>
              <div className="text-[9px] text-cyan-400/80 mt-0.5 flex items-center gap-1 font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <span>MediaPipe Face</span>
              </div>
            </div>
          </div>
        </div>

        {/* 2. CUSTOMER CLASSIFICATION & SEGMENTATION (2-Letter Code) */}
        <div className="mb-3 rounded-lg border border-cyan-500/30 bg-cyan-950/30 p-2">
          {isResolved ? (
            <>
              <div className="text-[10px] text-cyan-400/80 font-semibold tracking-wider uppercase mb-1 flex items-center justify-between">
                <span>{t("customer_segmentation")}</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded font-extrabold border ${segment.badgeColor}`}>
                  [{segment.code}]
                </span>
              </div>
              <div className="text-cyan-200 font-bold text-[12px] tracking-wide">
                {segment.title}
              </div>
              <div className="text-[10px] text-cyan-400/60 mt-0.5 leading-snug">
                {segment.incomeTier} • {segment.loyaltyTier}
              </div>
            </>
          ) : (
            <>
              <div className="text-[10px] text-amber-400/80 font-semibold tracking-wider uppercase mb-1 flex items-center justify-between">
                <span>{t("customer_segmentation")}</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded font-extrabold border border-amber-400/70 text-amber-300 bg-amber-950/40 animate-pulse">
                  {t("waiting_vector")}
                </span>
              </div>
              <div className="text-amber-200 font-bold text-[12px] tracking-wide">
                {t("extracting_features")}
              </div>
              <div className="text-[10px] text-amber-400/60 mt-0.5 leading-snug">
                {t("assign_segment_hint")}
              </div>
            </>
          )}
        </div>

        {/* 3. DATABASE SOURCE HEADER */}
        <div className="border-t border-cyan-500/30 pt-2 mb-2 flex items-center justify-between text-[9px] text-cyan-400/60 font-semibold tracking-widest uppercase">
          <span>CUSTOMERLENS DATABASE</span>
          <span className="text-emerald-400">● LIVE</span>
        </div>

        {/* 4. DETAILS SECTION (Phone, Email, Visits, Note) */}
        <div className="space-y-2 text-[11px] leading-snug">
          {/* Contact Details */}
          <div>
            <div className="text-[9px] text-cyan-400/60 uppercase font-semibold">{t("contact")}</div>
            <div className="text-emerald-300/90 font-medium">
              {phone} <span className="text-cyan-600">|</span> {email}
            </div>
          </div>

          {/* Visits & Spending Stats */}
          <div>
            <div className="text-[9px] text-cyan-400/60 uppercase font-semibold">
              {t("visits_spending")}
            </div>
            <div className="text-emerald-300/90 font-medium">
              {visits} {t("visits")} <span className="text-cyan-600">|</span> {spending}
            </div>
          </div>

          {/* Background / Personal Notes */}
          <div>
            <div className="text-[9px] text-cyan-400/60 uppercase font-semibold">
              {t("background_notes")}
            </div>
            <div className="text-emerald-300/90 font-medium line-clamp-3">{note}</div>
          </div>
        </div>

        {/* Click hint */}
        <div className="mt-3 pt-2 border-t border-cyan-500/20 text-[9px] text-cyan-400/50 text-center tracking-wider uppercase">
          ✓ Nhấn vào để chỉnh sửa thông tin
        </div>
      </div>
    </div>
  );
}
