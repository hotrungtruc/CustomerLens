"use client";

import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";

export default function NotificationsPage() {
  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="notifications" />
        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100">
          <PageHeader
            title="Thông báo"
            subtitle="Các thông báo hệ thống và cảnh báo khách hàng."
          />
          <div className="flex flex-1 items-center justify-center p-6">
            <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-slate-400 shadow-sm">
              Danh sách thông báo sẽ hiển thị ở đây.
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
