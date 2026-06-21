"use client";

import { useState } from "react";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import { Camera, Shield, Bell, UserCog, ChevronRight } from "lucide-react";

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

function SelectRow({ label, value, options }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-sm text-slate-700">{label}</span>
      <button className="flex shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50">
        {value}
        <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
      </button>
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

function InputRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-sm text-slate-700">{label}</span>
      <input
        defaultValue={value}
        className="w-40 rounded-md border border-slate-200 px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-400"
      />
    </div>
  );
}

export default function SettingsPage() {
  const [motion, setMotion] = useState(true);
  const [autoUpdate, setAutoUpdate] = useState(true);
  const [unknownAlert, setUnknownAlert] = useState(true);
  const [vipNotif, setVipNotif] = useState(true);
  const [emailAlert, setEmailAlert] = useState(false);
  const [soundAlert, setSoundAlert] = useState(true);

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="settings" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 bg-slate-50">
          <PageHeader
            title="Cài đặt hệ thống"
            subtitle="Cấu hình camera, nhận diện và quản lý tài khoản."
          />

          <div className="flex-1 min-h-0 overflow-hidden p-3 sm:p-4">
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
                  <SelectRow label="Độ phân giải mặc định" value="1080p" />
                  <SelectRow label="Tần số quét khuôn mặt" value="500ms" />
                  <SelectRow label="Lưu trữ video" value="30 ngày" />
                  <ToggleRow
                    label="Bật phát hiện chuyển động"
                    checked={motion}
                    onChange={setMotion}
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
                  <SelectRow label="Ngưỡng độ chính xác" value="85%" />
                  <SelectRow label="Chế độ phát hiện" value="Nhanh" />
                  <ToggleRow
                    label="Tự động cập nhật mẫu"
                    checked={autoUpdate}
                    onChange={setAutoUpdate}
                  />
                  <ToggleRow
                    label="Cảnh báo khuôn mặt lạ"
                    checked={unknownAlert}
                    onChange={setUnknownAlert}
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
                    checked={vipNotif}
                    onChange={setVipNotif}
                  />
                  <ToggleRow
                    label="Cảnh báo qua email"
                    checked={emailAlert}
                    onChange={setEmailAlert}
                  />
                  <ToggleRow
                    label="Âm thanh cảnh báo"
                    checked={soundAlert}
                    onChange={setSoundAlert}
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
                  <InputRow label="Tên quản trị viên" value="Admin" />
                  <InputRow label="Email" value="admin@frontdesk.ai" />
                  <InputRow label="Đổi mật khẩu" value="••••••••" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
