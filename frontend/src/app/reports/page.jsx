"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ReportsRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950 text-slate-400">
      Redirecting...
    </div>
  );
}
