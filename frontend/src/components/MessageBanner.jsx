export default function MessageBanner({
  message,
  variant = "info",
  className = "",
}) {
  const styles = {
    success: "bg-emerald-100 text-emerald-800",
    warning: "bg-amber-100 text-amber-800",
    error: "bg-rose-100 text-rose-800",
    info: "bg-slate-100 text-slate-700",
  };

  return (
    <div
      className={`rounded-xl px-4 py-3 text-sm font-medium ${styles[variant]} ${className}`}
    >
      {message}
    </div>
  );
}
