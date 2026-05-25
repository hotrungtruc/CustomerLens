import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCustomerInfo, postCheckIn } from "../services/api";

export function useCustomerDetection() {
  const [status, setStatus] = useState("idle");
  const [customer, setCustomer] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [checkInState, setCheckInState] = useState("idle");
  const timerRef = useRef(null);

  const pollCustomer = useCallback(async () => {
    try {
      const data = await fetchCustomerInfo();
      if (data.status === "success") {
        setStatus("success");
        setCustomer(data);
        setError("");
      } else {
        setStatus(data.status || "idle");
        setCustomer(null);
      }
    } catch (err) {
      setError("Unable to reach the backend");
    }
  }, []);

  useEffect(() => {
    pollCustomer();
    timerRef.current = setInterval(pollCustomer, 500);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [pollCustomer]);

  const checkIn = useCallback(async () => {
    setCheckInState("loading");
    setMessage("");
    try {
      const data = await postCheckIn();
      setCheckInState(data.success ? "success" : "warning");
      setMessage(data.message || "");
      if (data.success) {
        await pollCustomer();
      }
    } catch (err) {
      setCheckInState("error");
      setMessage("Unable to send check-in request");
    }
  }, [pollCustomer]);

  return {
    status,
    customer,
    message,
    error,
    checkIn,
    checkInState,
  };
}
