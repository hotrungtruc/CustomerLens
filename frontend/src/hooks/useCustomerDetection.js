import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCustomersOverview } from "../services/api";

export function useCustomerDetection() {
  const [status, setStatus] = useState("idle");
  const [customers, setCustomers] = useState([]);
  const [error, setError] = useState("");
  const timerRef = useRef(null);
  const lastSuccessRef = useRef(0);
  const lastCustomersRef = useRef([]);
  const graceMs = 2500;

  const pollCustomers = useCallback(async () => {
    try {
      const data = await fetchCustomersOverview();
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
  }, []);

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
    error,
  };
}
