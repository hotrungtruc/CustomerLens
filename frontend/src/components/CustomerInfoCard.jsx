import MessageBanner from "./MessageBanner";

const emptyState = {
  title: "Waiting for a face",
  detail: "Customer details will appear after a successful match.",
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
        <h2 className="text-2xl">Customer profile</h2>
        <span className="text-xs uppercase tracking-[0.35em] text-ink/50">
          {status === "success" ? "Detected" : "Waiting"}
        </span>
      </div>

      {error && (
        <MessageBanner variant="error" message={error} className="mb-4" />
      )}

      {hasCustomer ? (
        <div className="flex flex-1 flex-col gap-5">
          {customer.image ? (
            <img
              src={`data:image/jpeg;base64,${customer.image}`}
              alt={customer.name}
              className="h-56 w-full rounded-2xl object-cover"
            />
          ) : (
            <div className="flex h-56 items-center justify-center rounded-2xl border border-dashed border-ink/20 text-ink/50">
              No photo available
            </div>
          )}

          <div className="rounded-2xl bg-ink px-5 py-4 text-sand">
            <div className="grid gap-3 text-sm">
              <InfoRow label="Name" value={customer.name} />
              <InfoRow label="Customer ID" value={customer.id} />
              <InfoRow label="Phone" value={customer.phone} />
              <InfoRow label="Visit count" value={customer.visit_count} />
              <InfoRow label="Last visit" value={customer.last_visit} />
            </div>
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
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-ink/10 bg-white/60 text-center text-ink/60">
          <p className="text-lg font-medium">{emptyState.title}</p>
          <p className="max-w-xs text-sm">{emptyState.detail}</p>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-white/20 pb-2 last:border-b-0">
      <span className="text-sand/70">{label}</span>
      <span className="text-right text-sand">{value ?? "-"}</span>
    </div>
  );
}
