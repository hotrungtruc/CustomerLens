import { useState, useEffect, useCallback } from "react";

export function useServerStatus() {
  const [status, setStatus] = useState("checking"); // checking | online | offline | waking
  const [error, setError] = useState(null);

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/server/status");
      if (!res.ok) throw new Error("HTTP error " + res.status);
      const data = await res.json();
      if (data.success) {
        if (data.state === "running") {
          setStatus("online");
        } else if (data.state === "pending") {
          setStatus("waking");
        } else {
          setStatus("offline");
        }
      } else {
        setStatus("offline");
      }
    } catch (err) {
      setStatus("offline");
      setError(err.message);
    }
  }, []);

  const wakeServer = async () => {
    setStatus("waking");
    try {
      const res = await fetch("/api/server/wake", { method: "POST" });
      const data = await res.json();
      if (!data.success) {
        setError(data.error || "Gửi lệnh không thành công");
        setStatus("offline");
      }
    } catch (err) {
      setError("Không thể gửi lệnh đánh thức: " + err.message);
      setStatus("offline");
    }
  };

  useEffect(() => {
    checkStatus();
  }, [checkStatus]);

  useEffect(() => {
    let timer;
    if (status === "waking" || status === "checking") {
      timer = setInterval(checkStatus, 5000);
    }
    return () => clearInterval(timer);
  }, [status, checkStatus]);

  return { status, wakeServer, checkStatus, error };
}
