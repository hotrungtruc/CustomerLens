"use client";

import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";

export default function NotificationsPage() {
  return (
    <main className="min-h-screen bg-slate-50 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-[1400px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid lg:grid-cols-[220px_minmax(0,1fr)]">
        <Sidebar active="notifications" />
        <div className="flex min-w-0 flex-col">
          <PageHeader title="Thông báo" subtitle="Các thông báo hệ thống và cảnh báo khách hàng." />
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
