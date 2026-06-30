"use client";

import { useState, useEffect } from "react";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import { Camera, Shield, Bell, UserCog, ChevronRight } from "lucide-react";
import { fetchSettings, updateSettings } from "../../services/api";

function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-10 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${
        checked ? "bg-blue-600" : "bg-slate-200"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 translate-y-0.5 rounded-full bg-white shadow transition-transform duration-200 ${
          checked ? "translate-x-4.5" : "translate-x-0.5"
        }`}
        style={{ transform: `translateX(${checked ? "18px" : "2px"})` }}
      />
    </button>
  );
}

function SelectRow({ label, value, options, onChange }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-sm text-slate-700">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 outline-none focus:border-blue-400 cursor-pointer"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function ToggleRow({ label, checked, onChange }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-sm text-slate-700">{label}</span>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

function InputRow({ label, value, onChange, type = "text", step = "any" }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-sm text-slate-700">{label}</span>
      <input
        type={type}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-40 rounded-md border border-slate-200 px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-400"
      />
    </div>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    camera_resolution: "1080p",
    process_every_n_frames: 1,
    video_storage_days: 30,
    motion_detection: true,
    similarity_threshold: 0.50,
    detection_mode: "Nhanh",
    auto_update_template: true,
    unknown_face_alert: true,
    vip_notification: true,
    email_alert: false,
    sound_alert: true,
  });
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings()
      .then((data) => {
        setSettings(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load settings", err);
        setLoading(false);
      });
  }, []);

  const handleChange = (key, value) => {
    // If it's a number input, convert
    let val = value;
    if (key === "process_every_n_frames" || key === "video_storage_days") {
      val = parseInt(value) || 0;
    } else if (key === "similarity_threshold") {
      val = parseFloat(value) || 0;
    }
    
    setSettings((prev) => ({ ...prev, [key]: val }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateSettings(settings);
      // Optional: Show success toast
    } catch (err) {
      console.error("Failed to update settings", err);
      // Optional: Show error toast
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="settings" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 bg-slate-50">
          <PageHeader
            title="Cài đặt hệ thống"
            subtitle="Cấu hình camera, nhận diện và quản lý tài khoản."
            action={
              <button
                onClick={handleSave}
                disabled={loading || saving}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "Đang lưu..." : "Lưu cài đặt"}
              </button>
            }
          />

          <div className="flex-1 min-h-0 overflow-hidden p-3 sm:p-4">
            {loading ? (
              <div className="flex h-full items-center justify-center text-slate-500">Đang tải cài đặt...</div>
            ) : (
              <div className="grid h-full min-h-0 grid-rows-4 gap-3 lg:grid-cols-2 lg:grid-rows-2">
                {/* Camera settings */}
                <div className="min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50">
                      <Camera className="h-4 w-4 text-blue-600" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      Cài đặt Camera
                    </h3>
                  </div>
                  <div className="mt-2 divide-y divide-slate-50">
                    <SelectRow 
                      label="Độ phân giải mặc định" 
                      value={settings.camera_resolution} 
                      onChange={(v) => handleChange("camera_resolution", v)}
                      options={[
                        { label: "1080p", value: "1080p" },
                        { label: "720p", value: "720p" }
                      ]}
                    />
                    <InputRow 
                      label="Tần số quét khuôn mặt (frames)" 
                      type="number"
                      value={settings.process_every_n_frames} 
                      onChange={(v) => handleChange("process_every_n_frames", v)}
                    />
                    <InputRow 
                      label="Lưu trữ video (ngày)" 
                      type="number"
                      value={settings.video_storage_days} 
                      onChange={(v) => handleChange("video_storage_days", v)}
                    />
                    <ToggleRow
                      label="Bật phát hiện chuyển động"
                      checked={settings.motion_detection}
                      onChange={(v) => handleChange("motion_detection", v)}
                    />
                  </div>
                </div>

                {/* Face recognition */}
                <div className="min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50">
                      <Shield className="h-4 w-4 text-blue-600" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      Nhận diện khuôn mặt
                    </h3>
                  </div>
                  <div className="mt-2 divide-y divide-slate-50">
                    <InputRow 
                      label="Ngưỡng độ chính xác (0 - 1.0)" 
                      type="number"
                      step="0.01"
                      value={settings.similarity_threshold} 
                      onChange={(v) => handleChange("similarity_threshold", v)}
                    />
                    <SelectRow 
                      label="Chế độ phát hiện" 
                      value={settings.detection_mode} 
                      onChange={(v) => handleChange("detection_mode", v)}
                      options={[
                        { label: "Nhanh", value: "Nhanh" },
                        { label: "Chậm", value: "Chậm" },
                        { label: "Chính xác cao", value: "Chính xác cao" }
                      ]}
                    />
                    <ToggleRow
                      label="Tự động cập nhật mẫu"
                      checked={settings.auto_update_template}
                      onChange={(v) => handleChange("auto_update_template", v)}
                    />
                    <ToggleRow
                      label="Cảnh báo khuôn mặt lạ"
                      checked={settings.unknown_face_alert}
                      onChange={(v) => handleChange("unknown_face_alert", v)}
                    />
                  </div>
                </div>

                {/* Notifications */}
                <div className="min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50">
                      <Bell className="h-4 w-4 text-blue-600" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      Thông báo
                    </h3>
                  </div>
                  <div className="mt-2 divide-y divide-slate-50">
                    <ToggleRow
                      label="Thông báo khách VIP"
                      checked={settings.vip_notification}
                      onChange={(v) => handleChange("vip_notification", v)}
                    />
                    <ToggleRow
                      label="Cảnh báo qua email"
                      checked={settings.email_alert}
                      onChange={(v) => handleChange("email_alert", v)}
                    />
                    <ToggleRow
                      label="Âm thanh cảnh báo"
                      checked={settings.sound_alert}
                      onChange={(v) => handleChange("sound_alert", v)}
                    />
                  </div>
                </div>

                {/* Account */}
                <div className="min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50">
                      <UserCog className="h-4 w-4 text-blue-600" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      Tài khoản & Phân quyền
                    </h3>
                  </div>
                  <div className="mt-2 divide-y divide-slate-50">
                    <InputRow label="Tên quản trị viên" value="Admin" onChange={() => {}} />
                    <InputRow label="Email" value="admin@frontdesk.ai" onChange={() => {}} />
                    <InputRow label="Đổi mật khẩu" value="••••••••" type="password" onChange={() => {}} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
