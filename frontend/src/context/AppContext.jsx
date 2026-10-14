"use client";

import React, { createContext, useContext, useState, useEffect } from "react";

export const translations = {
  en: {
    app_title: "CustomerLens",
    app_subtitle: "Smart Front-Door AI",
    camera_live: "Camera Live",
    live_feed: "LIVE FEED",
    recent_customers: "Recent Customers",
    view_all: "View All",
    analyzing_faces: "Analyzing faces...",
    no_customers_in_frame: "No customers in camera view",
    identifying: "IDENTIFYING...",
    add_details: "Add Details +",
    view_profile: "View Profile →",
    new_guest: "New Guest",
    guest: "Guest",
    member: "Member",
    vip: "VIP",
    client: "CLIENT",
    device_recovery: "Recover Device",
    recover_old_camera: "Recover Old Camera",
    enter_pairing_code_desc: "Enter 6-digit code created by administrator.",
    pairing_code_placeholder: "000000",
    pair_btn: "Pair",
    pairing_invalid: "Invalid pairing code",
    device_identifying: "Identifying device...",
    admin_only_alert: "Only Administrator accounts have permission to access customer details or registration.",
    add_customer_title: "Add New Customer",
    customer_name_label: "Customer Name",
    customer_name_placeholder: "John Doe",
    phone_label: "Phone Number",
    phone_placeholder: "0901 234 567",
    email_label: "Email",
    email_placeholder: "example@email.com",
    tier_label: "Loyalty Tier",
    cancel_btn: "Cancel",
    save_btn: "Save Info",
    saving_btn: "Saving...",
    name_required_error: "Please enter customer name.",
    save_failed_error: "Save failed, please try again.",
    nav_overview: "Overview",
    nav_camera: "Camera",
    nav_customers: "Customers",
    nav_history: "History",
    nav_authorization: "Authorization",
    nav_reports: "Reports",
    nav_settings: "Settings",
    login_btn: "Login",
    logout_btn: "Logout",
    toggle_theme_dark: "Switch to Dark Mode",
    toggle_theme_light: "Switch to Light Mode",
    toggle_lang_vi: "Chuyển sang Tiếng Việt",
    toggle_lang_en: "Switch to English",
    notifications: "Notifications",
    settings_title: "System Settings",
    history_title: "Activity History",
    customers_title: "Customer Directory",
    reports_title: "Business Reports",
    authorization_title: "Device & Role Authorization",
  },
  vi: {
    app_title: "CustomerLens",
    app_subtitle: "AI Nhận Diện Cửa Thông Minh",
    camera_live: "Camera trực tiếp",
    live_feed: "TRỰC TIẾP",
    recent_customers: "Khách hàng gần đây",
    view_all: "Xem tất cả",
    analyzing_faces: "Đang phân tích khuôn mặt...",
    no_customers_in_frame: "Chưa có khách nào trong khung hình",
    identifying: "ĐANG NHẬN DIỆN...",
    add_details: "Thêm thông tin +",
    view_profile: "Xem hồ sơ →",
    new_guest: "Khách Mới",
    guest: "Khách",
    member: "Thành viên",
    vip: "VIP",
    client: "KHÁCH",
    device_recovery: "Khôi phục thiết bị",
    recover_old_camera: "Khôi phục camera cũ",
    enter_pairing_code_desc: "Nhập mã 6 số do quản trị viên tạo.",
    pairing_code_placeholder: "000000",
    pair_btn: "Ghép",
    pairing_invalid: "Mã ghép nối không hợp lệ",
    device_identifying: "Đang nhận diện thiết bị…",
    admin_only_alert: "Chỉ tài khoản Quản trị viên (Admin) mới có quyền truy cập thông tin chi tiết hoặc đăng ký khách hàng.",
    add_customer_title: "Thêm khách hàng mới",
    customer_name_label: "Tên khách hàng",
    customer_name_placeholder: "Nguyễn Văn A",
    phone_label: "Số điện thoại",
    phone_placeholder: "0901 234 567",
    email_label: "Email",
    email_placeholder: "example@email.com",
    tier_label: "Hạng khách hàng",
    cancel_btn: "Huỷ",
    save_btn: "Lưu thông tin",
    saving_btn: "Đang lưu...",
    name_required_error: "Vui lòng nhập tên khách hàng.",
    save_failed_error: "Lưu thất bại, vui lòng thử lại.",
    nav_overview: "Tổng quan",
    nav_camera: "Camera",
    nav_customers: "Khách hàng",
    nav_history: "Lịch sử",
    nav_authorization: "Phân quyền",
    nav_reports: "Báo cáo",
    nav_settings: "Cài đặt",
    login_btn: "Đăng nhập",
    logout_btn: "Đăng xuất",
    toggle_theme_dark: "Chuyển sang giao diện tối",
    toggle_theme_light: "Chuyển sang giao diện sáng",
    toggle_lang_vi: "Chuyển sang Tiếng Việt",
    toggle_lang_en: "Switch to English",
    notifications: "Thông báo",
    settings_title: "Cài đặt hệ thống",
    history_title: "Lịch sử ra vào",
    customers_title: "Danh sách khách hàng",
    reports_title: "Báo cáo doanh thu & khách hàng",
    authorization_title: "Phân quyền & Thiết bị",
  },
};

const AppContext = createContext({
  lang: "en",
  theme: "light",
  toggleLang: () => {},
  toggleTheme: () => {},
  t: (key) => key,
});

export function AppProvider({ children }) {
  const [lang, setLang] = useState("en");
  const [theme, setTheme] = useState("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // 1. Load language preference (Default: 'en')
    const savedLang = localStorage.getItem("customerlens_lang") || "en";
    setLang(savedLang);

    // 2. Load theme preference (Default: 'light')
    const savedTheme = localStorage.getItem("customerlens_theme") || "light";
    setTheme(savedTheme);
    if (savedTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }

    setMounted(true);
  }, []);

  const toggleLang = () => {
    const nextLang = lang === "en" ? "vi" : "en";
    setLang(nextLang);
    localStorage.setItem("customerlens_lang", nextLang);
  };

  const toggleTheme = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    localStorage.setItem("customerlens_theme", nextTheme);
    if (nextTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  const t = (key) => {
    return translations[lang]?.[key] || translations["en"]?.[key] || key;
  };

  return (
    <AppContext.Provider
      value={{
        lang,
        theme,
        toggleLang,
        toggleTheme,
        t,
        mounted,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  return useContext(AppContext);
}
