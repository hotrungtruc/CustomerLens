import MessageBanner from "./MessageBanner";

const emptyState = {
  title: "Khách mới",
  detail: "Chưa có dữ liệu khách hàng.",
};

export default function CustomerInfoCard({
  status,
  customer,
  message,
  checkIn,
  checkInState,
  error,
}) {
  const hasCustomer = status === "success" && customer;
  const messageVariant =
    checkInState === "success"
      ? "success"
      : checkInState === "error"
        ? "error"
        : "warning";

  return (
    <div className="flex h-full flex-col">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-copper/15 text-copper">
            <span className="text-lg font-semibold">👤</span>
          </div>
          <div>
            <h2 className="text-2xl">Khách mới</h2>
            <p className="text-xs uppercase tracking-[0.3em] text-ink/45">
              Thông tin khách hàng
            </p>
          </div>
        </div>
        <span className="rounded-full border border-copper/20 bg-copper/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.22em] text-copper">
          {status === "success" ? "CHUẨN ĐK" : "CHƯA ĐK"}
        </span>
      </div>

      {error && (
        <MessageBanner variant="error" message={error} className="mb-4" />
      )}

      {hasCustomer ? (
        <div className="flex flex-1 flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <StatBox label="Mã KH" value={customer.id} />
            <StatBox label="Tên" value={customer.name} />
            <StatBox label="SĐT" value={customer.phone} />
            <StatBox label="Lần đến" value={customer.visit_count} />
          </div>

          <div className="rounded-2xl border border-dashed border-copper/25 bg-copper/5 px-5 py-4 text-sm text-ink/75">
            <p className="mb-1 text-xs uppercase tracking-[0.3em] text-copper/70">
              Ghi chú
            </p>
            <p className="leading-6">
              Lần đến gần nhất: <span className="font-medium text-ink">{customer.last_visit}</span>
            </p>
          </div>

          <button
            type="button"
            onClick={checkIn}
            disabled={checkInState === "loading"}
            className="rounded-xl bg-copper px-6 py-3 text-base font-semibold text-white shadow-lg transition hover:-translate-y-0.5 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-60"
          >
            {checkInState === "loading" ? "Processing..." : "Check in"}
          </button>

          {message && (
            <MessageBanner
              variant={messageVariant}
              message={message}
            />
          )}
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
