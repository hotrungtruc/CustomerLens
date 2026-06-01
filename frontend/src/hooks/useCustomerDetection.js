import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCustomersOverview, postNewGuest } from "../services/api";

export function useCustomerDetection() {
  const [status, setStatus]       = useState("idle");
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [error, setError]         = useState("");

  // ── Selection + frozen (từ file cũ) ──────────────────────────────────────
  // selectedTrackId: track_id của ô đang được chọn
  const [selectedTrackId, setSelectedTrackId] = useState(null);

  // frozenCustomer: snapshot customer tại thời điểm nhấn vào ô
  // Giữ nguyên kể cả khi ô sidebar biến mất — chỉ xóa khi Lưu/Bỏ qua
  const [frozenCustomer, setFrozenCustomer] = useState(null);

  // ── Guest form state ──────────────────────────────────────────────────────
  const [guestForm, setGuestForm]     = useState({ name: "", phone: "", email: "" });
  const [guestSubmit, setGuestSubmit] = useState("idle"); // idle|loading|success|error
  const [guestMsg, setGuestMsg]       = useState("");

  // ── Polling refs ──────────────────────────────────────────────────────────
  const timerRef         = useRef(null);
  const lastSuccessRef   = useRef(0);
  const lastCustomersRef = useRef([]);
  const graceMs          = 2500;

  const pollCustomers = useCallback(async () => {
    try {
      const data = await fetchCustomersOverview();

      if (data.frame_size?.width && data.frame_size?.height) {
        setFrameSize({ width: data.frame_size.width, height: data.frame_size.height });
      }

      if (data.status === "success") {
        setStatus("success");
        setCustomers(data.customers || []);
        setError("");
        lastSuccessRef.current   = Date.now();
        lastCustomersRef.current = data.customers || [];
      } else {
        const stillFresh = Date.now() - lastSuccessRef.current <= graceMs;
        if (stillFresh && lastCustomersRef.current.length > 0) {
          setStatus("success");
          setCustomers(lastCustomersRef.current);
        } else {
          setStatus(data.status || "idle");
          setCustomers([]);
          lastCustomersRef.current = [];
        }
      }
    } catch {
      setError("Unable to reach the backend");
    }
  }, []);

  useEffect(() => {
    pollCustomers();
    timerRef.current = setInterval(pollCustomers, 250);
    return () => clearInterval(timerRef.current);
  }, [pollCustomers]);

  // ── selectedCustomer: ưu tiên frozenCustomer khi form đang mở ────────────
  const selectedCustomer =
    frozenCustomer ??
    customers.find((c) => c.track_id === selectedTrackId) ??
    null;

  // ── isGuest helper ────────────────────────────────────────────────────────
  const isGuest = (customer) =>
    customer?.id?.startsWith("GUEST_") && customer?.name === "Guest";

  // ── Nhấn vào ô sidebar ────────────────────────────────────────────────────
  const selectCustomer = useCallback((customer) => {
    if (selectedTrackId === customer.track_id) {
      // Nhấn lại ô đang chọn → bỏ chọn, xóa frozen
      setSelectedTrackId(null);
      setFrozenCustomer(null);
      setGuestForm({ name: "", phone: "", email: "" });
      setGuestSubmit("idle");
      setGuestMsg("");
    } else {
      // Chọn ô mới → freeze snapshot ngay
      setSelectedTrackId(customer.track_id);
      setFrozenCustomer(customer);
      setGuestForm({ name: "", phone: "", email: "" });
      setGuestSubmit("idle");
      setGuestMsg("");
    }
  }, [selectedTrackId]);

  // ── Đăng ký khách mới ────────────────────────────────────────────────────
  const submitGuest = useCallback(async () => {
    const guestId = frozenCustomer?.id ?? selectedCustomer?.id;
    if (!guestId) return;
    setGuestSubmit("loading");
    setGuestMsg("");
    try {
      // promote embedding trước (không throw nếu lỗi)
      try {
        const { promoteGuest } = await import("../services/api");
        await promoteGuest(guestId);
      } catch {
        console.warn("Promote failed, continuing...");
      }
      // lưu thông tin
      const res = await postNewGuest({ ...guestForm, guest_id: guestId });
      setGuestSubmit("success");
      setGuestMsg(res.message || "Đã lưu thông tin!");
      setGuestForm({ name: "", phone: "", email: "" });
      setTimeout(() => {
        setSelectedTrackId(null);
        setFrozenCustomer(null);
        setGuestSubmit("idle");
        setGuestMsg("");
        pollCustomers();
      }, 2000);
    } catch {
      setGuestSubmit("error");
      setGuestMsg("Lưu thất bại, thử lại.");
    }
  }, [frozenCustomer, selectedCustomer, guestForm, pollCustomers]);

  // ── Bỏ qua đăng ký ───────────────────────────────────────────────────────
  const skipGuest = useCallback(() => {
    setSelectedTrackId(null);
    setFrozenCustomer(null);
    setGuestForm({ name: "", phone: "", email: "" });
    setGuestSubmit("idle");
    setGuestMsg("");
  }, []);

  return {
    // polling state (giữ nguyên từ file mới)
    status,
    customers,
    frameSize,
    error,
    refreshCustomers: pollCustomers,

    // selection + frozen (từ file cũ)
    selectedTrackId,
    selectCustomer,       // dùng thay cho setSelectedTrackId trực tiếp
    selectedCustomer,
    isGuest,

    // guest form
    guestForm,
    setGuestForm,
    guestSubmit,
    guestMsg,
    submitGuest,
    skipGuest,
  };
}
