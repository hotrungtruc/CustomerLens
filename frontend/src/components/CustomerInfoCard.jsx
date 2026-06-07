import MessageBanner from "./MessageBanner";
import { useEffect, useMemo, useState } from "react";
import { putCustomerProfile } from "../services/api";

const emptyState = {
  title: "Chua co khach duoc nhan dang",
  detail: "Thong tin khach se hien thi thanh cac o khi camera nhan dien.",
};

const TRACK_BADGE_THEMES = [
  "bg-sky-500",
  "bg-fuchsia-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-indigo-500",
  "bg-rose-500",
];

function getTrackBadge(trackId) {
  const safeTrack = Number(trackId || 0);
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  return {
    symbol: safeTrack > 0 ? alphabet[(safeTrack - 1) % alphabet.length] : "?",
    tone: TRACK_BADGE_THEMES[safeTrack % TRACK_BADGE_THEMES.length],
  };
}

export default function CustomerInfoCard({
  status,
  customers,
  error,
  refreshCustomers,
  onSelectTrack,
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedTileId, setSelectedTileId] = useState(null);
  const [frozenCustomer, setFrozenCustomer] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [saveVariant, setSaveVariant] = useState("success");
  const [form, setForm] = useState({
    name: "",
    phone: "",
    note: "",
  });
  const hasCustomers = status === "success" && customers.length > 0;

  const liveSelectedCustomer = useMemo(() => {
    if (!customers.length) {
      return null;
    }
    if (!selectedTileId) {
      return customers[0];
    }
    return customers.find((item) => item.tile_id === selectedTileId) || null;
  }, [customers, selectedTileId]);

  const selectedCustomer = useMemo(() => {
    if (frozenCustomer) {
      return frozenCustomer;
    }
    if (liveSelectedCustomer) {
      return liveSelectedCustomer;
    }
    if (!customers.length) {
      return null;
    }
    return customers[0];
  }, [customers, frozenCustomer, liveSelectedCustomer]);

  const openDetail = (tileId) => {
    const nextCustomer = customers.find((item) => item.tile_id === tileId) || null;
    setSelectedTileId(tileId);
    setFrozenCustomer(nextCustomer);
    setIsExpanded(true);
  };

  useEffect(() => {
    if (liveSelectedCustomer) {
      setFrozenCustomer(liveSelectedCustomer);
      return;
    }

    if (!selectedTileId) {
      setFrozenCustomer(null);
    }
  }, [liveSelectedCustomer, selectedTileId]);

  useEffect(() => {
    if (!selectedCustomer || isEditing) {
      return;
    }
    setForm({
      name: selectedCustomer.name || "",
      phone: selectedCustomer.phone || "",
      note: selectedCustomer.note || "",
    });
  }, [isEditing, selectedCustomer]);

  useEffect(() => {
    if (!onSelectTrack) {
      return;
    }
    if (!selectedCustomer) {
      onSelectTrack(null);
      return;
    }
    onSelectTrack(selectedCustomer.track_id);
  }, [onSelectTrack, selectedCustomer]);

  const rankLabel = (count) => {
    const value = Number(count || 0);
    if (value >= 30) {
      return "VIP";
    }
    if (value >= 10) {
      return "Than thiet";
    }
    return "Standard";
  };

  const onStartEdit = () => {
    if (!selectedCustomer) {
      return;
    }
    setSaveMessage("");
    setForm({
      name: selectedCustomer.name || "",
      phone: selectedCustomer.phone || "",
      note: selectedCustomer.note || "",
    });
    setIsEditing(true);
  };

  const onCancelEdit = () => {
    setIsEditing(false);
    setSaveMessage("");
    if (!selectedCustomer) {
      return;
    }
    setForm({
      name: selectedCustomer.name || "",
      phone: selectedCustomer.phone || "",
      note: selectedCustomer.note || "",
    });
  };

  const onSaveProfile = async () => {
    const trimmedName = (form.name || "").trim();
    if (!trimmedName) {
      setSaveVariant("warning");
      setSaveMessage("Vui long nhap ten khach hang");
      return;
    }

    setIsSaving(true);
    setSaveMessage("");

    try {
      const response = await putCustomerProfile({
        id: selectedCustomer?.id,
        source_id: selectedCustomer?.id,
        name: trimmedName,
        phone: form.phone,
        note: form.note,
      });

      if (!response.success) {
        setSaveVariant("error");
        setSaveMessage(response.message || "Khong the cap nhat khach hang");
        return;
      }

      if (response.created) {
        setSaveVariant("success");
        setSaveMessage(`Da tao ma KH moi: ${response.customer.id}`);
      } else {
        setSaveVariant("success");
        setSaveMessage("Da cap nhat thong tin khach hang");
      }

      setIsEditing(false);
      if (refreshCustomers) {
        await refreshCustomers();
      }
    } catch (saveError) {
      setSaveVariant("error");
      setSaveMessage("Khong the ket noi backend de luu thong tin");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="relative flex h-full min-h-[640px] flex-col overflow-hidden">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-copper/15 text-copper">
            <span className="text-lg font-semibold">👤</span>
          </div>
          <div>
            <h2 className="text-2xl">Ket qua nhan dang</h2>
            <p className="text-xs uppercase tracking-[0.3em] text-ink/45">
              Danh sach khach hien tai
            </p>
          </div>
        </div>
        <span className="rounded-full border border-copper/20 bg-copper/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.22em] text-copper">
          {hasCustomers ? `${customers.length} KHACH` : "CHO NHAN DIEN"}
        </span>
      </div>

      {error && (
        <MessageBanner variant="error" message={error} className="mb-4" />
      )}

      {hasCustomers ? (
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          <div className="grid gap-4 md:grid-cols-2">
            {customers.map((item) => {
              const isSelected = selectedCustomer?.tile_id === item.tile_id;
              const detectedLabel = item.detected ? "Nhan ra" : "Chua DK";
              const detectedClass = item.detected
                ? "bg-emerald-100 text-emerald-700"
                : "bg-rose-100 text-rose-700";
              const { symbol, tone } = getTrackBadge(item.track_id);

              return (
                <button
                  key={item.tile_id}
                  type="button"
                  onClick={() => openDetail(item.tile_id)}
                  className={`rounded-2xl border bg-white p-4 text-left transition hover:-translate-y-0.5 hover:shadow-lg ${
                    isSelected
                      ? "border-emerald-400 shadow-[0_12px_30px_rgba(16,185,129,0.18)]"
                      : "border-black/5 shadow-[0_10px_20px_rgba(15,23,42,0.06)]"
                  }`}
                >
                  <div className="mb-4 flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold text-white ${tone}`}>
                          {symbol}
                        </span>
                        <p className="text-lg font-semibold text-ink">{item.name || "Khach moi"}</p>
                      </div>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${detectedClass}`}>
                      {detectedLabel}
                    </span>
                  </div>

                  <div className="space-y-2 text-sm text-ink/75">
                    <TileRow label="Ma KH" value={item.id} />
                    <TileRow label="Lan den" value={item.total_attendance} />
                    <TileRow label="Hang" value={rankLabel(item.total_attendance)} />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 rounded-3xl border border-dashed border-copper/20 bg-white/70 p-8 text-center text-ink/60">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-copper/10 text-copper">
            <span className="text-2xl">👤</span>
          </div>
          <p className="text-xl font-semibold text-ink">{emptyState.title}</p>
          <p className="max-w-xs text-sm leading-6">{emptyState.detail}</p>
        </div>
      )}

      <div className={`absolute inset-x-0 bottom-0 z-20 rounded-t-3xl border border-copper/20 bg-white/95 shadow-[0_-10px_30px_rgba(15,23,42,0.12)] backdrop-blur transition-all duration-300 ${isExpanded ? "h-[72%]" : "h-16"}`}>
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex h-16 w-full items-center justify-between px-5"
        >
          <div className="flex items-center gap-3">
            <span className="text-lg">👤</span>
            <span className="font-semibold text-ink">Thong tin khach hang</span>
          </div>
          <span className="text-xl text-ink/70">{isExpanded ? "⌄" : "⌃"}</span>
        </button>

        {isExpanded && selectedCustomer ? (
          <div className="h-[calc(100%-4rem)] overflow-y-auto border-t border-black/5 px-5 py-4">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold text-white ${getTrackBadge(selectedCustomer.track_id).tone}`}>
                    {getTrackBadge(selectedCustomer.track_id).symbol}
                  </span>
                  <h3 className="text-xl font-semibold text-ink">{selectedCustomer.name || "Khach moi"}</h3>
                </div>
                <p className="text-xs uppercase tracking-[0.2em] text-ink/45">Chi tiet khach duoc chon</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onStartEdit}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-black/10 bg-white text-lg text-ink transition hover:bg-slate-50"
                  title="Sua thong tin"
                >
                  ✎
                </button>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    selectedCustomer.detected
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-rose-100 text-rose-700"
                  }`}
                >
                  {selectedCustomer.detected ? "Nhan ra" : "Chua DK"}
                </span>
              </div>
            </div>

            {isEditing ? (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <EditField
                    label="Ten"
                    value={form.name}
                    onChange={(value) => setForm((prev) => ({ ...prev, name: value }))}
                    placeholder="Nhap ten khach hang"
                  />
                  <EditField
                    label="SDT"
                    value={form.phone}
                    onChange={(value) => setForm((prev) => ({ ...prev, phone: value }))}
                    placeholder="Nhap so dien thoai"
                  />
                </div>

                <EditField
                  label="Note"
                  value={form.note}
                  onChange={(value) => setForm((prev) => ({ ...prev, note: value }))}
                  placeholder="Thong tin ghi chu ve khach"
                  multiline
                />

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={onSaveProfile}
                    disabled={isSaving}
                    className="rounded-xl bg-copper px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isSaving ? "Dang luu..." : "Save"}
                  </button>
                  <button
                    type="button"
                    onClick={onCancelEdit}
                    disabled={isSaving}
                    className="rounded-xl border border-black/10 bg-white px-4 py-2 text-sm font-semibold text-ink transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                <StatBox label="Ma KH" value={selectedCustomer.id} />
                <StatBox label="Ten" value={selectedCustomer.name} />
                <StatBox label="SDT" value={selectedCustomer.phone} />
                <StatBox label="Nhom dich vu" value={selectedCustomer.service_category} />
                <StatBox label="Bat dau su dung" value={selectedCustomer.service_start_year} />
                <StatBox label="Tham nien" value={selectedCustomer.customer_tenure_years} />
                <StatBox label="Hang khach" value={selectedCustomer.loyalty_tier || rankLabel(selectedCustomer.total_attendance)} />
                <StatBox label="Note" value={selectedCustomer.note} />
                <StatBox label="Lan den" value={selectedCustomer.total_attendance} />
                <StatBox label="Lan cuoi" value={selectedCustomer.last_attendance_time} />
              </div>
            )}

            {saveMessage ? <MessageBanner variant={saveVariant} message={saveMessage} className="mt-4" /> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function StatBox({ label, value }) {
  return (
    <div className="rounded-2xl border border-black/5 bg-white px-4 py-4 shadow-[0_10px_25px_rgba(15,23,42,0.04)]">
      <div className="mb-2 text-xs uppercase tracking-[0.24em] text-ink/45">
        {label}
      </div>
      <div className="text-base font-semibold text-ink">
        {value ?? "Chưa có"}
      </div>
    </div>
  );
}

function TileRow({ label, value }) {
  return (
    <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2">
      <span className="text-xs uppercase tracking-[0.18em] text-ink/50">{label}</span>
      <span className="font-semibold text-ink">{value ?? "-"}</span>
    </div>
  );
}

function EditField({ label, value, onChange, placeholder, multiline = false }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-ink/45">{label}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          rows={3}
          className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-copper"
        />
      ) : (
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-copper"
        />
      )}
    </label>
  );
}
