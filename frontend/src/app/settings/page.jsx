"use client";

import { useState, useEffect } from "react";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import { Camera, Shield, Settings2, Activity } from "lucide-react";
import { fetchSettings, updateSettings } from "../../services/api";

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
    process_every_n_frames: 1,
    similarity_threshold: 0.50,
    min_face_bbox_size: 50,
    min_detection_score: 0.30,
    track_buffer_size: 2,
    track_iou_threshold: 0.3,
    guest_creation_buffer_size: 10,
    guest_min_detection_score: 0.85,
    guest_min_face_bbox_size: 100,
    new_guest_debounce_seconds: 4,
    new_guest_debounce_similarity: 0.38,
    checkin_cooldown_seconds: 30,
    customer_profile_hold_seconds: 2.5,
  });
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings()
      .then((data) => {
        setSettings((prev) => ({ ...prev, ...data }));
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load settings", err);
        setLoading(false);
      });
  }, []);

  const handleChange = (key, value) => {
    const floatKeys = [
      "similarity_threshold", "min_detection_score", "track_iou_threshold", 
      "guest_min_detection_score", "new_guest_debounce_similarity",
      "customer_profile_hold_seconds"
    ];
    const intKeys = [
      "process_every_n_frames", "min_face_bbox_size", "track_buffer_size",
      "guest_creation_buffer_size", "guest_min_face_bbox_size", 
      "new_guest_debounce_seconds", "checkin_cooldown_seconds"
    ];

    let val = value;
    if (intKeys.includes(key)) {
      val = parseInt(value) || 0;
    } else if (floatKeys.includes(key)) {
      val = parseFloat(value) || 0;
    }
    
    setSettings((prev) => ({ ...prev, [key]: val }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateSettings(settings);
    } catch (err) {
      console.error("Failed to update settings", err);
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
            subtitle="Cấu hình hệ thống nhận diện."
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

          <div className="flex-1 min-h-0 overflow-y-auto p-3 sm:p-4">
            {loading ? (
              <div className="flex h-full items-center justify-center text-slate-500">Đang tải cài đặt...</div>
            ) : (
              <div className="grid h-fit min-h-0 gap-4 lg:grid-cols-2">
                {/* Camera & Tracking */}
                <div className="min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50">
                      <Camera className="h-4 w-4 text-blue-600" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      Camera & Tracking
                    </h3>
                  </div>
                  <div className="mt-2 divide-y divide-slate-50">
                    <InputRow 
                      label="Tần số quét khuôn mặt (frames)" 
                      type="number"
                      value={settings.process_every_n_frames} 
                      onChange={(v) => handleChange("process_every_n_frames", v)}
                    />
                    <InputRow 
                      label="Kích thước khuôn mặt tối thiểu (px)" 
                      type="number"
                      value={settings.min_face_bbox_size} 
                      onChange={(v) => handleChange("min_face_bbox_size", v)}
                    />
                    <InputRow 
                      label="Ngưỡng tự tin phát hiện tối thiểu" 
                      type="number" step="0.01"
                      value={settings.min_detection_score} 
                      onChange={(v) => handleChange("min_detection_score", v)}
                    />
                    <InputRow 
                      label="Bộ nhớ đệm tracking (frames)" 
                      type="number"
                      value={settings.track_buffer_size} 
                      onChange={(v) => handleChange("track_buffer_size", v)}
                    />
                    <InputRow 
                      label="Ngưỡng IOU tracking" 
                      type="number" step="0.01"
                      value={settings.track_iou_threshold} 
                      onChange={(v) => handleChange("track_iou_threshold", v)}
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
                      type="number" step="0.01"
                      value={settings.similarity_threshold} 
                      onChange={(v) => handleChange("similarity_threshold", v)}
                    />
                  </div>
                </div>

                {/* Guest Processing */}
                <div className="min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50">
                      <Settings2 className="h-4 w-4 text-blue-600" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      Chế độ Khách (Strict Mode)
                    </h3>
                  </div>
                  <div className="mt-2 divide-y divide-slate-50">
                    <InputRow 
                      label="Bộ nhớ đệm tạo Khách (frames)" 
                      type="number"
                      value={settings.guest_creation_buffer_size} 
                      onChange={(v) => handleChange("guest_creation_buffer_size", v)}
                    />
                    <InputRow 
                      label="Ngưỡng tự tin Khách tối thiểu" 
                      type="number" step="0.01"
                      value={settings.guest_min_detection_score} 
                      onChange={(v) => handleChange("guest_min_detection_score", v)}
                    />
                    <InputRow 
                      label="Kích thước mặt Khách tối thiểu (px)" 
                      type="number"
                      value={settings.guest_min_face_bbox_size} 
                      onChange={(v) => handleChange("guest_min_face_bbox_size", v)}
                    />
                    <InputRow 
                      label="Thời gian chờ Khách mới (giây)" 
                      type="number"
                      value={settings.new_guest_debounce_seconds} 
                      onChange={(v) => handleChange("new_guest_debounce_seconds", v)}
                    />
                    <InputRow 
                      label="Ngưỡng tránh trùng lặp Khách" 
                      type="number" step="0.01"
                      value={settings.new_guest_debounce_similarity} 
                      onChange={(v) => handleChange("new_guest_debounce_similarity", v)}
                    />
                  </div>
                </div>

                {/* Application Logic */}
                <div className="min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50">
                      <Activity className="h-4 w-4 text-blue-600" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      Ứng dụng & Thời gian
                    </h3>
                  </div>
                  <div className="mt-2 divide-y divide-slate-50">
                    <InputRow 
                      label="Thời gian chờ check-in lại (giây)" 
                      type="number"
                      value={settings.checkin_cooldown_seconds} 
                      onChange={(v) => handleChange("checkin_cooldown_seconds", v)}
                    />
                    <InputRow 
                      label="Thời gian giữ hồ sơ hiển thị (giây)" 
                      type="number" step="0.1"
                      value={settings.customer_profile_hold_seconds} 
                      onChange={(v) => handleChange("customer_profile_hold_seconds", v)}
                    />
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
