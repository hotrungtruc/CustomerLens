"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Sidebar from "../components/Sidebar";
import PageHeader from "../components/PageHeader";
import CameraStream from "../components/CameraStream";
import { KeyRound, X } from "lucide-react";
import { getTrackBadge } from "../lib/trackBadge";
import {
  claimDeviceEnrollment,
  putCustomerProfile,
  resolveDeviceIdentity,
} from "../services/api";
import { useProfilePrefetch } from "../hooks/useProfilePrefetch";

// Phân biệt khách cũ vs khách mới
function isKnownCustomer(c) {
  return c.id && /^\d{1,3}$/.test(String(c.id));
}

function rankLabel(visitCount) {
  const n = Number(visitCount || 0);
  if (n >= 30) return "VIP";
  if (n >= 10) return "Member";
  return "Guest";
}

const RANK_COLORS = {
  VIP: "bg-yellow-100 text-yellow-700",
  Member: "bg-blue-100 text-blue-700",
  Guest: "bg-slate-100 text-slate-600",
};

function Stars({ count }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <svg
          key={i}
          viewBox="0 0 12 12"
          className={`h-3 w-3 ${i < count ? "fill-amber-400" : "fill-slate-200"}`}
        >
          <path d="M6 1l1.4 2.9 3.2.5-2.3 2.2.5 3.2L6 8.2l-2.8 1.6.5-3.2L1.4 4.4l3.2-.5z" />
        </svg>
      ))}
    </div>
  );
}

// ── Popup thêm khách mới ──────────────────────────────────────────────────────
function AddCustomerModal({ customer, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: "",
    phone: "",
    email: "",
    rank: "Guest",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const { symbol, theme } = getTrackBadge(customer.track_id);

  const handleChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) {
      setError("Vui lòng nhập tên khách hàng.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const result = await putCustomerProfile({
        id: customer.id,
        source_id: customer.id,
        track_id: customer.track_id,
        name: form.name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        rank: form.rank,
      });
      onSaved(result);
    } catch (err) {
      setError("Lưu thất bại, vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  };

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold text-white ring-2 ring-white ${theme.base}`}
            >
              {symbol}
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800">
                Thêm khách hàng mới
              </p>
              <p className="text-xs text-slate-400">{customer.id}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
          >
            <svg
              viewBox="0 0 16 16"
              className="h-4 w-4 fill-none stroke-current"
              strokeWidth="2"
            >
              <path d="M3 3l10 10M13 3L3 13" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <div className="space-y-4 px-6 py-5">
          {/* Tên */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              Tên khách hàng <span className="text-red-500">*</span>
            </label>
            <input
              name="name"
              value={form.name}
              onChange={handleChange}
              placeholder="Nguyễn Văn A"
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-blue-400"
            />
          </div>

          {/* SĐT */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              Số điện thoại
            </label>
            <input
              name="phone"
              value={form.phone}
              onChange={handleChange}
              placeholder="0901 234 567"
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-blue-400"
            />
          </div>

          {/* Email */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              Email
            </label>
            <input
              name="email"
              value={form.email}
              onChange={handleChange}
              placeholder="example@email.com"
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-blue-400"
            />
          </div>

          {/* Hạng */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              Hạng khách hàng
            </label>
            <div className="flex gap-2">
              {["Guest", "Member", "VIP"].map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setForm((prev) => ({ ...prev, rank: r }))}
                  className={`flex-1 rounded-xl border py-2 text-sm font-medium transition ${
                    form.rank === r
                      ? "border-blue-500 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-xs text-red-600">
              {error}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 border-t border-slate-100 px-6 py-4">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Huỷ
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="flex-1 rounded-xl bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Đang lưu..." : "Lưu & Xem hồ sơ"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Customer card trong right panel ──────────────────────────────────────────
function CustomerCard({ c, onClick }) {
  const known = isKnownCustomer(c);
  const rank = rankLabel(c.visit_count);
  const starCount = rank === "VIP" ? 5 : rank === "Member" ? 4 : 3;
  const { symbol, theme } = getTrackBadge(c.track_id);
  const detectedAt = c.detected_at
    ? new Date(c.detected_at).toLocaleTimeString("vi-VN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "";

  return (
    <button
      onClick={() => onClick(c)}
      className="flex w-full items-center gap-3 px-5 py-3.5 text-left hover:bg-slate-50 transition-colors"
    >
      {/* Badge khớp bounding box */}
      <div
        className={`h-10 w-10 shrink-0 flex items-center justify-center rounded-full text-sm font-bold text-white ring-2 ring-white ${theme.base}`}
      >
        {symbol}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="truncate text-sm font-medium text-slate-800">
              {known ? c.name || `Khách #${c.id}` : "Khách Mới"}
            </span>
            <span
              className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${RANK_COLORS[rank]}`}
            >
              {rank}
            </span>
          </div>
          {detectedAt && (
            <span className="shrink-0 text-[10px] text-slate-400">
              {detectedAt}
            </span>
          )}
        </div>

        <span className="text-xs text-slate-400">
          {known ? `CLIENT_${c.id}` : c.id || "—"}
        </span>

        <div className="mt-0.5 flex items-center justify-between">
          <Stars count={starCount} />
          {/* Gợi ý hành động */}
          <span
            className={`text-[10px] font-medium ${known ? "text-blue-500" : "text-amber-500"}`}
          >
            {known ? "Xem hồ sơ →" : "Thêm thông tin +"}
          </span>
        </div>
      </div>
    </button>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const router = useRouter();
  const [cameraIdentity, setCameraIdentity] = useState(null);
  const [identityError, setIdentityError] = useState("");
  const [pairingCode, setPairingCode] = useState("");
  const [claimingPairing, setClaimingPairing] = useState(false);
  const [pairingError, setPairingError] = useState("");
  const [showPairingForm, setShowPairingForm] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadIdentity() {
      try {
        const identity = await resolveDeviceIdentity();
        if (!cancelled) setCameraIdentity(identity);
      } catch (error) {
        if (!cancelled) {
          setIdentityError(
            error instanceof Error
              ? error.message
              : "Không thể nhận diện thiết bị",
          );
        }
      }
    }

    loadIdentity();
    return () => {
      cancelled = true;
    };
  }, []);

  const handlePairingClaim = async () => {
    setClaimingPairing(true);
    setPairingError("");
    try {
      const identity = await claimDeviceEnrollment(pairingCode.trim());
      setCameraIdentity(identity);
      setIdentityError("");
      setPairingCode("");
    } catch (error) {
      setPairingError(
        error instanceof Error ? error.message : "Mã ghép nối không hợp lệ",
      );
    } finally {
      setClaimingPairing(false);
    }
  };

  // customers / frameSize are pushed up via the onCustomersChange callback from
  // CameraStream (which now owns the WebSocket connection internally).
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [highlightedTrackId, setHighlightedTrackId] = useState(null);
  const [modalCustomer, setModalCustomer] = useState(null);

  // Active prefetch: background-fetches full profiles for recognised faces
  // so that clicking a customer card navigates instantly.
  const { getProfile } = useProfilePrefetch(customers);

  const handleCustomersChange = useCallback((newCustomers, newFrameSize) => {
    setCustomers(newCustomers);
    setFrameSize(newFrameSize);
  }, []);

  const handleSelectTrack = useCallback((id) => setHighlightedTrackId(id), []);

  const validCustomers = customers.filter((c) => c.id != null);
  const recentCustomers = validCustomers.slice(0, 4);

  // Click vào card trong right panel
  const handleCardClick = useCallback(
    (c) => {
      const role = localStorage.getItem("role") || "guest";
      if (role !== "admin") {
        alert(
          "Chỉ tài khoản Quản trị viên (Admin) mới có quyền truy cập thông tin chi tiết hoặc đăng ký khách hàng.",
        );
        return;
      }
      setHighlightedTrackId(c.track_id);
      if (isKnownCustomer(c)) {
        // Stash prefetched profile so the detail page can render instantly
        const prefetched = getProfile(c.id);
        if (prefetched) {
          try {
            sessionStorage.setItem(
              `prefetch_profile_${c.id}`,
              JSON.stringify(prefetched),
            );
          } catch (_) {}
        }
        router.push(`/customers/${c.id}`);
      } else {
        // Khách mới → mở popup nhập thông tin
        setModalCustomer(c);
      }
    },
    [router, getProfile],
  );

  // Sau khi lưu thành công → navigate đến trang hồ sơ mới
  const handleSaved = useCallback(
    (result) => {
      setModalCustomer(null);
      const newId = result?.customer_id || result?.id;
      if (newId) {
        router.push(`/customers/${newId}`);
      } else {
        router.push("/customers");
      }
    },
    [router],
  );

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)_320px]">
        {/* Cột 1: Sidebar */}
        <Sidebar active="overview" />

        {/* Cột 2: Main */}
        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100">
          <PageHeader
            title="Smart Front-door AI"
          />

          <div className="flex-1 min-h-0 overflow-hidden bg-slate-950 relative mb-6">
            {cameraIdentity?.is_new || identityError ? (
              showPairingForm ? (
                <div className="absolute right-3 bottom-3 z-20 w-64 rounded-xl border border-white/15 bg-slate-950/85 p-3 text-white shadow-xl backdrop-blur">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold">Khôi phục camera cũ</p>
                    <button
                      type="button"
                      onClick={() => setShowPairingForm(false)}
                      className="text-slate-400 hover:text-white"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-300">
                    Nhập mã 6 số do quản trị viên tạo.
                  </p>
                  <div className="mt-2 flex gap-2">
                    <input
                      value={pairingCode}
                      onChange={(event) =>
                        setPairingCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                      }
                      placeholder="000000"
                      inputMode="numeric"
                      className="min-w-0 flex-1 rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-xs tracking-[0.2em] outline-none focus:border-blue-400"
                    />
                    <button
                      type="button"
                      onClick={handlePairingClaim}
                      disabled={pairingCode.length !== 6 || claimingPairing}
                      className="rounded-lg bg-blue-500 px-2.5 py-1.5 text-xs font-semibold disabled:opacity-40"
                    >
                      Ghép
                    </button>
                  </div>
                  {pairingError ? (
                    <p className="mt-2 text-[11px] text-rose-300">{pairingError}</p>
                  ) : null}
                </div>
              ) : (
                <button
                  onClick={() => setShowPairingForm(true)}
                  className="absolute right-3 bottom-3 z-20 flex items-center gap-1.5 rounded-full bg-slate-900/60 px-3 py-1.5 text-white/80 shadow-sm backdrop-blur hover:bg-slate-900/80 hover:text-white transition-all"
                  title="Khôi phục camera cũ"
                >
                  <KeyRound className="w-3.5 h-3.5" />
                  <span className="text-[11px] font-medium">Khôi phục thiết bị</span>
                </button>
              )
            ) : null}
            {identityError ? (
              <div className="flex h-full items-center justify-center px-6 text-center text-sm text-rose-300">
                {identityError}
              </div>
            ) : cameraIdentity ? (
              <CameraStream
                cameraId={cameraIdentity.camera_id}
                highlightedTrackId={highlightedTrackId}
                framed={false}
                fullHeight={true}
                onCustomersChange={handleCustomersChange}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-300">
                Đang nhận diện thiết bị…
              </div>
            )}
          </div>
        </div>

        {/* Cột 3: Right panel */}
        <div className="hidden min-h-0 flex-col lg:flex">
          <div className="border-b border-slate-100 px-4 py-4 xl:px-5 xl:py-5">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-800">
                Khách hàng gần đây
              </span>
              <Link
                href="/customers"
                className="text-xs font-medium text-blue-600 hover:underline"
              >
                Xem tất cả
              </Link>
            </div>
          </div>

          <div className="flex min-h-0 flex-col divide-y divide-slate-50 overflow-y-auto">
            {recentCustomers.length > 0 ? (
              recentCustomers.map((c) => (
                <CustomerCard
                  key={c.tile_id ?? c.track_id}
                  c={c}
                  onClick={handleCardClick}
                />
              ))
            ) : customers.length > 0 ? (
              <div className="px-5 py-8 text-center text-xs text-slate-400 animate-pulse">
                Đang phân tích khuôn mặt...
              </div>
            ) : (
              <div className="px-5 py-8 text-center text-xs text-slate-400">
                Chưa có khách nào trong khung hình
              </div>
            )}
          </div>

          {/* CTA bottom */}
          <div className="mt-auto border-t border-slate-100 p-4 xl:p-5">
            <p className="text-sm font-semibold text-slate-800">
              Thông tin khách hàng
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Theo dõi lịch sử và thông tin chi tiết từng lần ghé thăm.
            </p>
            <Link
              href="/customers"
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4 fill-none stroke-current"
                strokeWidth="2"
              >
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
              Xem chi tiết
            </Link>
          </div>
        </div>
      </div>

      {/* Popup thêm khách mới */}
      {modalCustomer && (
        <AddCustomerModal
          customer={modalCustomer}
          onClose={() => setModalCustomer(null)}
          onSaved={handleSaved}
        />
      )}
    </main>
  );
}
