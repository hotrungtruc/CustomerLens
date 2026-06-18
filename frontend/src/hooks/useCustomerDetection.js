import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCustomersOverview } from "../services/api";
export function useCustomerDetection(cameraId = null) {
  const [status, setStatus] = useState("idle");
  const [customers, setCustomers] = useState([]);
  const [frameSize, setFrameSize] = useState({ width: 640, height: 360 });
  const [error, setError] = useState("");
  const timerRef = useRef(null);
  const lastSuccessRef = useRef(0);
  const lastCustomersRef = useRef([]);
  const graceMs = 2500;
  const pollCustomers = useCallback(async () => {
    try {
      const data = await fetchCustomersOverview(cameraId);
      if (data.frame_size?.width && data.frame_size?.height) {
        setFrameSize({
          width: data.frame_size.width,
          height: data.frame_size.height,
        });
      }
      if (data.status === "success") {
        setStatus("success");
        setCustomers(data.customers || []);
        setError("");
        lastSuccessRef.current = Date.now();
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
    } catch (err) {
      setError("Unable to reach the backend");
    }
  }, [cameraId]);
  useEffect(() => {
    pollCustomers();
    timerRef.current = setInterval(pollCustomers, 250);
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [pollCustomers]);
  return {
    status,
    customers,
    frameSize,
    error,
    refreshCustomers: pollCustomers,
  };
}