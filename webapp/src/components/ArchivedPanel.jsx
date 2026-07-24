import { X } from "lucide-react";

export default function ArchivedPanel({ sessions, onRestore, onPurge, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 md:items-center md:p-4">
      <div
        className="flex max-h-[80vh] w-full max-w-md flex-col rounded-t-2xl border border-border bg-surface shadow-xl md:rounded-2xl"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="text-sm font-semibold text-ink">Archived conversations</h2>
          <button onClick={onClose} className="text-faint hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {sessions.length === 0 && (
            <p className="px-2 py-6 text-center text-sm text-faint">Nothing archived</p>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className="mb-1 flex items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-raised"
            >
              <span className="min-w-0 flex-1 truncate text-muted">
                {s.title || "New conversation"}
              </span>
              <div className="ml-2 flex shrink-0 gap-2">
                <button
                  onClick={() => onRestore(s.id)}
                  className="text-xs text-muted hover:text-ink"
                >
                  Restore
                </button>
                <button
                  onClick={() => {
                    if (confirm("Permanently delete this conversation? This can't be undone."))
                      onPurge(s.id);
                  }}
                  className="text-xs text-danger hover:text-danger"
                >
                  Delete forever
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
