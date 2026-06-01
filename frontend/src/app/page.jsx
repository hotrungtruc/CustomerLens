"use client";

import { useState } from "react";
import CameraStream from "../components/CameraStream";
import PersonCard from "../components/PersonCard";
import DetailPanel from "../components/DetailPanel";
import { useCustomerDetection } from "../hooks/useCustomerDetection";

export default function HomePage() {
  const {
    status,
    customers,
    frameSize,
    error,
    refreshCustomers,
    selectedTrackId,
    selectCustomer,
    selectedCustomer,
    isGuest,
    guestForm,
    setGuestForm,
    guestSubmit,
    guestMsg,
    submitGuest,
    skipGuest,
  } = useCustomerDetection();

  const [detailOpen, setDetailOpen] = useState(true);

  const knownCount = customers.filter((c) => !isGuest(c)).length;
  const guestCount = customers.filter((c) => isGuest(c)).length;

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto max-w-7xl">

        {/* ── Header ── */}
        <header className="mb-8 flex items-start justify-between">
          <div className="flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulseSoft" />
            Đang hoạt động
          </div>

          <div className="text-center">
            <div className="mb-1 flex items-center justify-center gap-3">
              <div className="h-px w-8 bg-copper/40" />
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-copper">Front Desk</p>
              <div className="h-px w-8 bg-copper/40" />
            </div>
            <h1 className="text-3xl font-semibold text-ink md:text-4xl">Smart Front-door AI</h1>
            <p className="mt-1.5 text-sm text-ink/55">
              Giám sát camera lối vào và cập nhật thông tin khách hàng theo thời gian thực.
            </p>
          </div>

          <div className="flex items-center gap-2 rounded-full border border-ink/10 bg-white px-3 py-1.5 text-sm font-medium text-ink/70">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            {customers.length} người
          </div>
        </header>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <span>✕</span><span>{error}</span>
          </div>
        )}

        {/* ── 2-col layout ── */}
        <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr] items-stretch">

          {/* Left: Camera — truyền thêm customers + frameSize + highlightedTrackId từ file mới */}
          <section className="panel p-5 animate-floatIn">
            <div className="mb-4 flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-copper/10">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#b85c38" strokeWidth="1.5">
                  <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/>
                </svg>
              </div>
              <h2 className="text-base font-semibold text-ink">Camera lối vào</h2>
              <span className="ml-auto flex items-center gap-1.5 rounded-full bg-clay px-2.5 py-1 text-[10px] uppercase tracking-wide text-ink">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulseSoft" />
                Live
              </span>
            </div>
            <CameraStream
              customers={customers}
              frameSize={frameSize}
              highlightedTrackId={selectedTrackId}
            />
          </section>

          {/* Right: Results + Detail — 1 panel, flex column */}
          <section className="panel animate-floatIn flex flex-col overflow-hidden">

            {/* Kết quả nhận dạng */}
            <div className="p-5 flex-1">
              <div className="mb-3 flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-ink/5">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0f172a" strokeWidth="1.5">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>
                </div>
                <h2 className="text-base font-semibold text-ink">Kết quả nhận dạng</h2>
                {customers.length > 0 && (
                  <div className="ml-auto flex items-center gap-2 text-xs text-ink/40">
                    {knownCount > 0 && (
                      <span className="flex items-center gap-1">
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        {knownCount} nhận ra
                      </span>
                    )}
                    {guestCount > 0 && (
                      <span className="flex items-center gap-1">
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400" />
                        {guestCount} chưa đk
                      </span>
                    )}
                  </div>
                )}
              </div>

              {customers.length === 0 ? (
                <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-ink/10 bg-white/60 text-ink/40">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                  </svg>
                  <p className="text-sm">Đang chờ khuôn mặt...</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  {customers.slice(0, 6).map((c) => (
                    <PersonCard
                      key={c.track_id ?? c.id}
                      person={c}
                      isGuest={isGuest}
                      isSelected={selectedTrackId === c.track_id}
                      onClick={() => {
                        selectCustomer(c);
                        if (!detailOpen) setDetailOpen(true);
                      }}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Toggle bar */}
            <div className="border-t border-ink/[0.06]">
              <button
                type="button"
                onClick={() => setDetailOpen((v) => !v)}
                className="flex w-full items-center gap-2 px-5 py-3 transition hover:bg-ink/[0.02]"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#b85c38" strokeWidth="1.5">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
                </svg>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-copper">
                  Thông tin khách hàng
                </p>
                {selectedCustomer && isGuest(selectedCustomer) && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-semibold text-amber-700">
                    {customers.filter((c) => isGuest(c)).length} cần đăng ký
                  </span>
                )}
                <span className="ml-auto flex h-6 w-6 items-center justify-center rounded-full bg-red-500 transition hover:bg-red-600">
                  <svg
                    width="10" height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="white"
                    strokeWidth="2.5"
                    style={{ transform: detailOpen ? "rotate(0deg)" : "rotate(180deg)", transition: "transform 0.2s" }}
                  >
                    <polyline points="18 15 12 9 6 15" />
                  </svg>
                </span>
              </button>
            </div>

            {/* Detail panel body */}
            {detailOpen && (
              <div className="p-4 pt-0">
                <DetailPanel
                  person={selectedCustomer}
                  isGuest={isGuest}
                  guestForm={guestForm}
                  setGuestForm={setGuestForm}
                  guestSubmit={guestSubmit}
                  guestMsg={guestMsg}
                  submitGuest={submitGuest}
                  skipGuest={skipGuest}
                />
              </div>
            )}

          </section>
        </div>
      </div>
    </main>
  );
}
