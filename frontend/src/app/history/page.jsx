"use client";

import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";

export default function HistoryPage() {
  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="history" />
        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100">
          <PageHeader
            title="Lịch sử"
            subtitle="Xem lịch sử nhận diện và hoạt động camera."
          />
          <div className="flex flex-1 items-center justify-center p-6">
            <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-slate-400 shadow-sm">
              Lịch sử chi tiết sẽ hiển thị ở đây.
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
