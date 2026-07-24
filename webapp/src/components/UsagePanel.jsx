import { X } from "lucide-react";

function formatUsd(value) {
  if (value == null) return "—";
  return `$${value.toFixed(value < 1 ? 4 : 2)}`;
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-sm font-medium text-ink">{value}</span>
    </div>
  );
}

export default function UsagePanel({ data, loading, error, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 md:items-center md:p-4">
      <div
        className="w-full max-w-sm rounded-t-2xl border border-border bg-surface shadow-xl md:rounded-2xl"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="text-sm font-semibold text-ink">OpenRouter usage</h2>
          <button onClick={onClose} className="text-faint hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="p-4">
          {loading && <p className="py-6 text-center text-sm text-faint">Loading…</p>}
          {error && !loading && <p className="py-6 text-center text-sm text-danger">{error}</p>}
          {data && !loading && !error && (
            <>
              <div className="mb-4 rounded-xl bg-raised p-4">
                <p className="text-xs text-muted">Deposit remaining</p>
                <p className="mt-1 text-3xl font-semibold text-ink">
                  {formatUsd(data.deposit_remaining)}
                </p>
                {data.deposit_total != null && (
                  <p className="mt-1 text-xs text-faint">
                    of {formatUsd(data.deposit_total)} deposited
                  </p>
                )}
              </div>
              <div className="divide-y divide-border">
                <Row label="Today" value={formatUsd(data.usage_daily)} />
                <Row label="This week" value={formatUsd(data.usage_weekly)} />
                <Row label="This month" value={formatUsd(data.usage_monthly)} />
                <Row label="Projected this month" value={formatUsd(data.projected_monthly)} />
                {data.limit != null && (
                  <>
                    <Row label="Key spending limit" value={formatUsd(data.limit)} />
                    <Row label="Key limit remaining" value={formatUsd(data.limit_remaining)} />
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
