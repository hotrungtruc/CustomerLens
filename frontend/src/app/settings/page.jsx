"use client";

import { useState, useEffect } from "react";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import { Camera, Shield, Settings2, Activity, HelpCircle, Save, RotateCcw } from "lucide-react";
import { fetchSettings, updateSettings } from "../../services/api";
import { useApp } from "../../context/AppContext";

function InputRow({ label, value, onChange, type = "text", step = "any", tooltip }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <div className="flex items-center gap-1.5 group relative">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
        {tooltip && (
          <>
            <HelpCircle className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 cursor-help" />
            <div className="pointer-events-none absolute left-0 top-6 z-10 w-64 opacity-0 transition-opacity group-hover:opacity-100">
              <div className="rounded-md bg-slate-800 dark:bg-slate-750 px-3 py-2 text-xs text-white shadow-lg border border-slate-700">
                {tooltip}
                <div className="absolute -top-1 left-4 h-2 w-2 rotate-45 bg-slate-800 dark:bg-slate-750 border-t border-l border-slate-700"></div>
              </div>
            </div>
          </>
        )}
      </div>
      <input
        type={type}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-36 sm:w-40 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1.5 text-xs text-slate-800 dark:text-white outline-none focus:border-blue-500 z-0 relative transition-colors"
      />
    </div>
  );
}

export default function SettingsPage() {
  const { t } = useApp();
  const [settings, setSettings] = useState({
    process_every_n_frames: 1,
    similarity_threshold: 0.50,
    min_face_bbox_size: 28,
    min_detection_score: 0.55,
    track_buffer_size: 3,
    track_iou_threshold: 0.3,
    guest_creation_buffer_size: 4,
    guest_min_detection_score: 0.60,
    guest_min_face_bbox_size: 28,
    new_guest_debounce_seconds: 4,
    new_guest_debounce_similarity: 0.38,
    checkin_cooldown_seconds: 30,
    customer_profile_hold_seconds: 2.5,
    edge_crop_padding: 0.25,
    edge_send_interval_ms: 250,
  });
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadData = () => {
    setLoading(true);
    fetchSettings()
      .then((data) => {
        setSettings((prev) => ({ ...prev, ...data }));
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load settings", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleReload = () => {
    loadData();
  };

  const handleChange = (key, value) => {
    const floatKeys = [
      "similarity_threshold", "min_detection_score", "track_iou_threshold", 
      "guest_min_detection_score", "new_guest_debounce_similarity",
      "customer_profile_hold_seconds", "edge_crop_padding"
    ];
    const intKeys = [
      "process_every_n_frames", "min_face_bbox_size", "track_buffer_size",
      "guest_creation_buffer_size", "guest_min_face_bbox_size", 
      "new_guest_debounce_seconds", "checkin_cooldown_seconds", "edge_send_interval_ms"
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
      alert(t("settings_saved"));
    } catch (err) {
      console.error("Failed to update settings", err);
      alert(t("error_saving_settings") + " " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white dark:bg-slate-950 transition-colors duration-200">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="settings" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 relative">
          <PageHeader
            title={t("settings_page_title")}
            subtitle={t("settings_page_subtitle")}
          />

          <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-5 lg:p-6 pb-24">
            {loading ? (
              <div className="flex h-full items-center justify-center text-sm text-slate-400 animate-pulse">
                {t("loading_settings")}
              </div>
            ) : (
              <div className="grid h-fit min-h-0 gap-4 lg:grid-cols-2">
                {/* Camera & Tracking */}
                <div className="min-h-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm relative z-0 hover:z-10 transition-all">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400">
                      <Camera className="h-4 w-4" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      {t("camera_tracking_group")}
                    </h3>
                  </div>
                  <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
                    <InputRow 
                      label={t("process_every_n_frames")}
                      tooltip={t("process_every_n_frames_tip")}
                      type="number"
                      value={settings.process_every_n_frames} 
                      onChange={(v) => handleChange("process_every_n_frames", v)}
                    />
                    <InputRow 
                      label={t("min_face_bbox_size")}
                      tooltip={t("min_face_bbox_size_tip")}
                      type="number"
                      value={settings.min_face_bbox_size} 
                      onChange={(v) => handleChange("min_face_bbox_size", v)}
                    />
                    <InputRow 
                      label={t("min_detection_score")}
                      tooltip={t("min_detection_score_tip")}
                      type="number" step="0.01"
                      value={settings.min_detection_score} 
                      onChange={(v) => handleChange("min_detection_score", v)}
                    />
                    <InputRow 
                      label={t("track_buffer_size")}
                      tooltip={t("track_buffer_size_tip")}
                      type="number"
                      value={settings.track_buffer_size} 
                      onChange={(v) => handleChange("track_buffer_size", v)}
                    />
                    <InputRow 
                      label={t("track_iou_threshold")}
                      tooltip={t("track_iou_threshold_tip")}
                      type="number" step="0.01"
                      value={settings.track_iou_threshold} 
                      onChange={(v) => handleChange("track_iou_threshold", v)}
                    />
                  </div>
                </div>

                {/* Edge Tracking */}
                <div className="min-h-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm relative z-0 hover:z-10 transition-all">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-50 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400">
                      <Activity className="h-4 w-4" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      {t("edge_tracking_group")}
                    </h3>
                  </div>
                  <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
                    <InputRow 
                      label={t("edge_send_interval_ms")}
                      tooltip={t("edge_send_interval_ms_tip")}
                      type="number"
                      value={settings.edge_send_interval_ms} 
                      onChange={(v) => handleChange("edge_send_interval_ms", v)}
                    />
                    <InputRow 
                      label={t("edge_crop_padding")}
                      tooltip={t("edge_crop_padding_tip")}
                      type="number" step="0.05"
                      value={settings.edge_crop_padding} 
                      onChange={(v) => handleChange("edge_crop_padding", v)}
                    />
                  </div>
                </div>

                {/* Face recognition */}
                <div className="min-h-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm relative z-0 hover:z-10 transition-all">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400">
                      <Shield className="h-4 w-4" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      {t("face_recognition_group")}
                    </h3>
                  </div>
                  <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
                    <InputRow 
                      label={t("similarity_threshold")}
                      tooltip={t("similarity_threshold_tip")}
                      type="number" step="0.01"
                      value={settings.similarity_threshold} 
                      onChange={(v) => handleChange("similarity_threshold", v)}
                    />
                  </div>
                </div>

                {/* Guest Processing */}
                <div className="min-h-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm relative z-0 hover:z-10 transition-all">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400">
                      <Settings2 className="h-4 w-4" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      {t("guest_processing_group")}
                    </h3>
                  </div>
                  <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
                    <InputRow 
                      label={t("guest_creation_buffer_size")}
                      tooltip={t("guest_creation_buffer_size_tip")}
                      type="number"
                      value={settings.guest_creation_buffer_size} 
                      onChange={(v) => handleChange("guest_creation_buffer_size", v)}
                    />
                    <InputRow 
                      label={t("guest_min_detection_score")}
                      tooltip={t("guest_min_detection_score_tip")}
                      type="number" step="0.01"
                      value={settings.guest_min_detection_score} 
                      onChange={(v) => handleChange("guest_min_detection_score", v)}
                    />
                    <InputRow 
                      label={t("guest_min_face_bbox_size")}
                      tooltip={t("guest_min_face_bbox_size_tip")}
                      type="number"
                      value={settings.guest_min_face_bbox_size} 
                      onChange={(v) => handleChange("guest_min_face_bbox_size", v)}
                    />
                    <InputRow 
                      label={t("new_guest_debounce_seconds")}
                      tooltip={t("new_guest_debounce_seconds_tip")}
                      type="number"
                      value={settings.new_guest_debounce_seconds} 
                      onChange={(v) => handleChange("new_guest_debounce_seconds", v)}
                    />
                    <InputRow 
                      label={t("new_guest_debounce_similarity")}
                      tooltip={t("new_guest_debounce_similarity_tip")}
                      type="number" step="0.01"
                      value={settings.new_guest_debounce_similarity} 
                      onChange={(v) => handleChange("new_guest_debounce_similarity", v)}
                    />
                  </div>
                </div>

                {/* Application Logic */}
                <div className="min-h-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm relative z-0 hover:z-10 transition-all">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400">
                      <Activity className="h-4 w-4" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      {t("app_logic_group")}
                    </h3>
                  </div>
                  <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
                    <InputRow 
                      label={t("checkin_cooldown_seconds")}
                      tooltip={t("checkin_cooldown_seconds_tip")}
                      type="number"
                      value={settings.checkin_cooldown_seconds} 
                      onChange={(v) => handleChange("checkin_cooldown_seconds", v)}
                    />
                    <InputRow 
                      label={t("customer_profile_hold_seconds")}
                      tooltip={t("customer_profile_hold_seconds_tip")}
                      type="number" step="0.1"
                      value={settings.customer_profile_hold_seconds} 
                      onChange={(v) => handleChange("customer_profile_hold_seconds", v)}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Sticky action buttons at bottom right */}
          <div className="absolute bottom-6 right-6 flex items-center gap-3 z-50">
            <button
              onClick={handleReload}
              disabled={loading || saving}
              className="inline-flex items-center gap-1.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 shadow-sm disabled:opacity-50 transition-colors"
            >
              <RotateCcw className="h-4 w-4" />
              {t("discard_changes")}
            </button>
            <button
              onClick={handleSave}
              disabled={loading || saving}
              className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 shadow-md disabled:opacity-50 transition-colors"
            >
              <Save className="h-4 w-4" />
              {saving ? "..." : t("save_settings")}
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
