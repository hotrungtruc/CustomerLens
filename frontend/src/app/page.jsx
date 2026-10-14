"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Sidebar from "../components/Sidebar";
import CameraStream from "../components/CameraStream";
import DashboardHeader from "../components/dashboard/DashboardHeader";
import KpiCards from "../components/dashboard/KpiCards";
import HourlyTrafficChart from "../components/dashboard/HourlyTrafficChart";
import GuestMixChart from "../components/dashboard/GuestMixChart";
import RealtimeVipFeed from "../components/dashboard/RealtimeVipFeed";
import StaffAttendanceCard from "../components/dashboard/StaffAttendanceCard";
import { KeyRound, X, Camera, ExternalLink } from "lucide-react";
import { getTrackBadge } from "../lib/trackBadge";
import {
  claimDeviceEnrollment,
  putCustomerProfile,
  resolveDeviceIdentity,
  fetchReportsData,
} from "../services/api";
import { useProfilePrefetch } from "../hooks/useProfilePrefetch";
import { useApp } from "../context/AppContext";

function isKnownCustomer(c) {
  if (c.customer_type === "registered") return true;
  return c.id && /^\d{1,3}$/.test(String(c.id));
}

function rankLabel(visitCount) {
  const n = Number(visitCount || 0);
  if (n >= 30) return "VIP";
  if (n >= 10) return "Member";
  return "Guest";
}

const RANK_COLORS = {
  VIP: "bg-yellow-100 text-yellow-700 dark:bg-yellow-950/60 dark:text-yellow-400",
  Member: "bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-400",
  Guest: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

function Stars({ count }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <svg
          key={i}
          viewBox="0 0 12 12"
          className={`h-3 w-3 ${i < count ? "fill-amber-400" : "fill-slate-200 dark:fill-slate-700"}`}
        >
          <path d="M6 1l1.4 2.9 3.2.5-2.3 2.2.5 3.2L6 8.2l-2.8 1.6.5-3.2L1.4 4.4l3.2-.5z" />
        </svg>
      ))}
    </div>
  );
}

// ── Popup Modal: Add New Customer ─────────────────────────────────────────────
function AddCustomerModal({ customer, onClose, onSaved }) {
  const { t } = useApp();
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
      setError(t("name_required_error"));
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
      setError(t("save_failed_error"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl transition-colors">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold text-white ring-2 ring-white dark:ring-slate-800 ${theme.base}`}
            >
              {symbol}
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-white">
                {t("add_customer_title")}
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500">{customer.id}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-300">
              {t("customer_name_label")} <span className="text-red-500">*</span>
            </label>
            <input
              name="name"
              value={form.name}
              onChange={handleChange}
              placeholder={t("customer_name_placeholder")}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-800 dark:text-white outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-blue-400"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-300">
              {t("phone_label")}
            </label>
            <input
              name="phone"
              value={form.phone}
              onChange={handleChange}
              placeholder={t("phone_placeholder")}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-800 dark:text-white outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-blue-400"
            />
          </div>

          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl px-4 py-2 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            {t("cancel_btn")}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={saving}
            className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? t("saving_btn") : t("save_btn")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Customer Card (used in live camera sidebar) ─────────────────────────────────
function CustomerCard({ c, onClick }) {
  const { t, lang } = useApp();
  const known = isKnownCustomer(c);
  const rank = rankLabel(c.total_visits);
  const starCount = rank === "VIP" ? 5 : rank === "Member" ? 4 : 3;
  const { symbol, theme } = getTrackBadge(c.track_id);
  const detectedAt = c.detected_at
    ? new Date(c.detected_at).toLocaleTimeString(lang === "vi" ? "vi-VN" : "en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "";

  return (
    <button
      onClick={() => onClick(c)}
      className="flex w-full items-center gap-3 px-5 py-3.5 text-left hover:bg-slate-50 dark:hover:bg-slate-850/60 transition-colors"
    >
      <div
        className={`h-10 w-10 shrink-0 flex items-center justify-center rounded-full text-sm font-bold text-white ring-2 ring-white dark:ring-slate-800 overflow-hidden ${theme.base}`}
      >
        {c.faceImage ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={c.faceImage} alt="Face" className="w-full h-full object-cover" />
        ) : (
          symbol
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">
              {known ? c.name || `${t("client")} #${c.id}` : t("new_guest")}
            </span>
            <span
              className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${RANK_COLORS[rank]}`}
            >
              {rank}
            </span>
          </div>
          {detectedAt && (
            <span className="shrink-0 text-[10px] text-slate-400 dark:text-slate-500">
              {detectedAt}
            </span>
          )}
        </div>

        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 font-mono">
          {known ? `CLIENT_${c.id}` : c.id}
        </span>

        <div className="mt-0.5 flex items-center justify-between">
          <Stars count={starCount} />
          <span
            className={`text-[10px] font-medium ${known ? "text-blue-500 dark:text-blue-400" : "text-amber-500 dark:text-amber-400"}`}
          >
            {known ? t("view_profile") : t("add_details")}
          </span>
        </div>
      </div>
    </button>
  );
}

// ── Main Dashboard Page ───────────────────────────────────────────────────────
export default function DashboardPage() {
  const router = useRouter();
  const { t } = useApp();

  // Active View: "dashboard" (Executive Analytics) vs "camera" (Dedicated Live Stream)
  const [activeView, setActiveView] = useState("dashboard");
  const [selectedBranch, setSelectedBranch] = useState("Downtown Branch");

  // Device & Camera State
  const [cameraIdentity, setCameraIdentity] = useState(null);
  const [identityError, setIdentityError] = useState("");
  const [pairingCode, setPairingCode] = useState("");
  const [claimingPairing, setClaimingPairing] = useState(false);
  const [pairingError, setPairingError] = useState("");
  const [showPairingForm, setShowPairingForm] = useState(false);

  // Live Customers State (synced from CameraStream)
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [highlightedTrackId, setHighlightedTrackId] = useState(null);
  const [modalCustomer, setModalCustomer] = useState(null);

  // Analytics Reports Data
  const [reportsData, setReportsData] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function loadIdentity() {
      try {
        const identity = await resolveDeviceIdentity();
        if (!cancelled) setCameraIdentity(identity);
      } catch (error) {
        if (!cancelled) {
          setIdentityError(
            error instanceof Error ? error.message : t("device_identifying"),
          );
        }
      }
    }

    async function loadReports() {
      try {
        const res = await fetchReportsData();
        if (!cancelled && res?.data) {
          setReportsData(res.data);
        }
      } catch (err) {
        console.warn("Reports load fallback to live state:", err);
      }
    }

    loadIdentity();
    loadReports();

    return () => {
      cancelled = true;
    };
  }, [t]);

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
        error instanceof Error ? error.message : t("pairing_invalid"),
      );
    } finally {
      setClaimingPairing(false);
    }
  };

  const { getProfile } = useProfilePrefetch(customers);

  const handleCustomersChange = useCallback((newCustomers, newFrameSize) => {
    setCustomers(newCustomers);
    setFrameSize(newFrameSize);
  }, []);

  const validCustomers = customers.filter((c) => c.id != null);
  const recentCustomers = validCustomers.slice(0, 4);

  const handleCardClick = useCallback(
    (c) => {
      const role = localStorage.getItem("role") || "guest";
      if (role !== "admin") {
        alert(t("admin_only_alert"));
        return;
      }
      setHighlightedTrackId(c.track_id);
      if (isKnownCustomer(c)) {
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
        setModalCustomer(c);
      }
    },
    [router, getProfile, t],
  );

  return (
    <main className="h-dvh w-screen overflow-hidden bg-slate-50 dark:bg-slate-950 transition-colors duration-200">
      <div className="flex h-full w-full overflow-hidden">
        {/* Sidebar */}
        <Sidebar active="overview" />

        {/* Center / Main Content Area */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Header */}
          <DashboardHeader
            activeView={activeView}
            onViewChange={setActiveView}
            selectedBranch={selectedBranch}
            onBranchChange={setSelectedBranch}
          />

          {/* ── View 1: Executive Dashboard (Analytics & Feeds) ── */}
          {activeView === "dashboard" ? (
            <div className="flex-1 overflow-y-auto px-5 py-6">
              <div className="mx-auto max-w-7xl space-y-6">
                {/* Row 1: KPI Cards */}
                <KpiCards
                  reportsData={reportsData}
                  vipCount={reportsData?.vip_visits || 12}
                  footTraffic={reportsData?.total_visits || 1245}
                  staffVerified={18}
                  staffTotal={20}
                />

                {/* Row 2: Charts (Dual Grid 65% / 35%) */}
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.8fr)_minmax(0,1.2fr)]">
                  <HourlyTrafficChart hourlyData={reportsData?.hourly_data} />
                  <GuestMixChart
                    returningRate={reportsData?.repeat_rate || 74.2}
                    newRate={reportsData?.repeat_rate ? (100 - reportsData.repeat_rate) : 25.8}
                  />
                </div>

                {/* Row 3: Operational Feeds (Dual Grid 50% / 50%) */}
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <RealtimeVipFeed
                    liveVipList={validCustomers}
                    onSelectCustomer={handleCardClick}
                  />
                  <StaffAttendanceCard />
                </div>

                {/* Live Camera Quick Status Banner */}
                <div className="flex items-center justify-between rounded-2xl border border-slate-200/80 bg-gradient-to-r from-blue-500/10 via-indigo-500/5 to-transparent dark:border-slate-800 p-4 backdrop-blur">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-md shadow-blue-500/20">
                      <Camera className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-800 dark:text-white">
                        {t("edge_front_door_stream")}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {cameraIdentity ? `${t("active_node")}: ${cameraIdentity.camera_id}` : t("connected_monitoring")} • MediaPipe FaceLandmarker 60 FPS
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setActiveView("camera")}
                    className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-blue-700 transition-all"
                  >
                    <span>{t("live_stream_toggle")}</span>
                    <ExternalLink className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ) : (
            /* ── View 2: Dedicated Live Camera Stream & HUD ── */
            <div className="grid flex-1 min-h-0 overflow-hidden lg:grid-cols-[minmax(0,1fr)_320px]">
              {/* Camera Stream Column */}
              <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-slate-950">
                {cameraIdentity?.is_new || identityError ? (
                  showPairingForm ? (
                    <div className="absolute right-3 bottom-3 z-20 w-64 rounded-xl border border-white/15 bg-slate-950/85 p-3 text-white shadow-xl backdrop-blur">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold">{t("recover_old_camera")}</p>
                        <button
                          type="button"
                          onClick={() => setShowPairingForm(false)}
                          className="text-slate-400 hover:text-white"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <p className="mt-1 text-[11px] text-slate-300">
                        {t("enter_pairing_code_desc")}
                      </p>
                      <div className="mt-2 flex gap-2">
                        <input
                          value={pairingCode}
                          onChange={(e) =>
                            setPairingCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                          }
                          placeholder={t("pairing_code_placeholder")}
                          inputMode="numeric"
                          className="min-w-0 flex-1 rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 text-xs tracking-[0.2em] outline-none focus:border-blue-400"
                        />
                        <button
                          type="button"
                          onClick={handlePairingClaim}
                          disabled={pairingCode.length !== 6 || claimingPairing}
                          className="rounded-lg bg-blue-500 px-2.5 py-1.5 text-xs font-semibold disabled:opacity-40"
                        >
                          {t("pair_btn")}
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
                      title={t("recover_old_camera")}
                    >
                      <KeyRound className="w-3.5 h-3.5" />
                      <span className="text-[11px] font-medium">{t("device_recovery")}</span>
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
                    onCustomerClick={handleCardClick}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-slate-300">
                    {t("device_identifying")}
                  </div>
                )}
              </div>

              {/* Live Customer Sidebar Column */}
              <div className="hidden min-h-0 flex-col border-l border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 transition-colors lg:flex">
                <div className="border-b border-slate-100 dark:border-slate-800 px-4 py-4 xl:px-5 xl:py-5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-800 dark:text-white">
                      {t("recent_customers")}
                    </span>
                    <Link
                      href="/customers"
                      className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      {t("view_all")}
                    </Link>
                  </div>
                </div>

                <div className="flex min-h-0 flex-1 flex-col divide-y divide-slate-50 dark:divide-slate-800 overflow-y-auto">
                  {recentCustomers.length > 0 ? (
                    recentCustomers.map((c) => (
                      <CustomerCard
                        key={c.tile_id ?? c.track_id}
                        c={c}
                        onClick={handleCardClick}
                      />
                    ))
                  ) : customers.length > 0 ? (
                    <div className="px-5 py-8 text-center text-xs text-slate-400 dark:text-slate-500 animate-pulse">
                      {t("analyzing_faces")}
                    </div>
                  ) : (
                    <div className="px-5 py-8 text-center text-xs text-slate-400 dark:text-slate-500">
                      {t("no_customers_in_frame")}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modal: Add Customer Profile */}
      {modalCustomer && (
        <AddCustomerModal
          customer={modalCustomer}
          onClose={() => setModalCustomer(null)}
          onSaved={() => setModalCustomer(null)}
        />
      )}
    </main>
  );
}
