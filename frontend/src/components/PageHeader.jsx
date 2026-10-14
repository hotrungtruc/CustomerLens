"use client";

import { useApp } from "../context/AppContext";
import { Bell, Sun, Moon } from "lucide-react";

const TITLE_MAP = {
  "Smart Front-door AI": { en: "CustomerLens", vi: "CustomerLens" },
  "CustomerLens": { en: "CustomerLens", vi: "CustomerLens" },
  "Quản lý Camera": { en: "Camera Management", vi: "Quản lý Camera" },
  "Camera Management": { en: "Camera Management", vi: "Quản lý Camera" },
  "Quản lý Khách hàng": { en: "Customer Directory", vi: "Quản lý Khách hàng" },
  "Customer Directory": { en: "Customer Directory", vi: "Quản lý Khách hàng" },
  "Hồ sơ Khách hàng": { en: "Customer Profile", vi: "Hồ sơ Khách hàng" },
  "Customer Profile": { en: "Customer Profile", vi: "Hồ sơ Khách hàng" },
  "Lịch sử Nhận diện Real-Time": { en: "Real-Time Recognition History", vi: "Lịch sử Nhận diện Real-Time" },
  "Real-Time Recognition History": { en: "Real-Time Recognition History", vi: "Lịch sử Nhận diện Real-Time" },
  "Báo cáo & Thống kê F&B": { en: "F&B Business Reports & Analytics", vi: "Báo cáo & Thống kê F&B" },
  "F&B Business Reports & Analytics": { en: "F&B Business Reports & Analytics", vi: "Báo cáo & Thống kê F&B" },
  "Phân quyền": { en: "Device & Role Authorization", vi: "Phân quyền" },
  "Device & Role Authorization": { en: "Device & Role Authorization", vi: "Phân quyền" },
  "Cài đặt hệ thống": { en: "System Settings", vi: "Cài đặt hệ thống" },
  "System Settings": { en: "System Settings", vi: "Cài đặt hệ thống" },
};

const SUBTITLE_MAP = {
  "Theo dõi tất cả thiết bị đang kết nối vào hệ thống.": {
    en: "Monitor all connected devices across camera networks.",
    vi: "Theo dõi tất cả thiết bị đang kết nối vào hệ thống.",
  },
  "Danh sách toàn bộ khách hàng được nhận diện bởi hệ thống.": {
    en: "Directory of all customers identified across camera streams.",
    vi: "Danh sách toàn bộ khách hàng được nhận diện bởi hệ thống.",
  },
  "Thông tin chi tiết và lịch sử của khách hàng.": {
    en: "Detailed profile, biometric embeddings and visit records.",
    vi: "Thông tin chi tiết và lịch sử của khách hàng.",
  },
  "Quản lý và tra cứu nhật ký nhận diện khuôn mặt từ hệ thống camera.": {
    en: "Search and inspect real-time facial recognition verification logs.",
    vi: "Quản lý và tra cứu nhật ký nhận diện khuôn mặt từ hệ thống camera.",
  },
  "Phân tích lưu lượng khách hàng, giờ cao điểm và tỷ lệ khách thân thiết thực tế từ cơ sở dữ liệu.": {
    en: "Analyze customer foot-traffic, peak hours and loyalty retention rates.",
    vi: "Phân tích lưu lượng khách hàng, giờ cao điểm và tỷ lệ khách thân thiết thực tế từ cơ sở dữ liệu.",
  },
  "Quản lý moderator và camera được phép theo dõi.": {
    en: "Manage moderator accounts and authorized camera streaming nodes.",
    vi: "Quản lý moderator và camera được phép theo dõi.",
  },
  "Cấu hình hệ thống nhận diện.": {
    en: "Configure edge AI thresholds and facial recognition pipeline.",
    vi: "Cấu hình hệ thống nhận diện.",
  },
};

export default function PageHeader({ title, subtitle }) {
  const { lang, theme, toggleLang, toggleTheme, t } = useApp();

  const currentLang = lang || "en";
  const displayTitle = TITLE_MAP[title]?.[currentLang] || title || t("app_title") || "CustomerLens";
  const displaySubtitle = SUBTITLE_MAP[subtitle]?.[currentLang] || subtitle;

  return (
    <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 sm:px-6 lg:px-6 lg:py-3.5 transition-colors duration-200">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
          {displayTitle}
        </h1>
        {displaySubtitle && (
          <p className="mt-0.5 max-w-2xl text-xs sm:text-sm text-slate-500 dark:text-slate-400">
            {displaySubtitle}
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        {/* 1. Theme Toggle (Sun / Moon) */}
        <button
          type="button"
          onClick={toggleTheme}
          title={theme === "dark" ? t("toggle_theme_light") : t("toggle_theme_dark")}
          className="relative inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition shadow-sm cursor-pointer"
        >
          {theme === "dark" ? (
            <Sun className="h-4 w-4 text-amber-400 transition-transform hover:rotate-45" />
          ) : (
            <Moon className="h-4 w-4 text-slate-600 dark:text-slate-300 transition-transform hover:-rotate-12" />
          )}
        </button>

        {/* 2. Circular Flag Toggle (UK / Vietnam) */}
        <button
          type="button"
          onClick={toggleLang}
          title={lang === "en" ? t("toggle_lang_vi") : t("toggle_lang_en")}
          className="relative inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:ring-2 hover:ring-blue-400/40 transition shadow-sm overflow-hidden p-1 cursor-pointer"
        >
          {lang === "en" ? (
            /* Circular UK Flag Badge (1:1 circular aspect) */
            <svg viewBox="0 0 36 36" className="w-full h-full rounded-full shadow-inner" fill="none">
              <circle cx="18" cy="18" r="18" fill="#012169" />
              <path d="M0,0 L36,36 M36,0 L0,36" stroke="#FFFFFF" strokeWidth="5.5" />
              <path d="M0,0 L36,36 M36,0 L0,36" stroke="#C8102E" strokeWidth="2.2" />
              <path d="M18,0 V36 M0,18 H36" stroke="#FFFFFF" strokeWidth="9" />
              <path d="M18,0 V36 M0,18 H36" stroke="#C8102E" strokeWidth="5.5" />
            </svg>
          ) : (
            /* Circular Vietnam Flag Badge (1:1 circular aspect) */
            <svg viewBox="0 0 36 36" className="w-full h-full rounded-full shadow-inner" fill="none">
              <circle cx="18" cy="18" r="18" fill="#DA251D" />
              <polygon
                fill="#FFCD00"
                points="18,7.5 21.2,14.1 28.5,15.1 23.2,20.3 24.5,27.5 18,24.1 11.5,27.5 12.8,20.3 7.5,15.1 14.8,14.1"
              />
            </svg>
          )}
        </button>

        {/* 3. Notification Bell */}
        <button
          type="button"
          title={t("notifications")}
          className="relative inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition shadow-sm cursor-pointer"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
        </button>
      </div>
    </div>
  );
}
