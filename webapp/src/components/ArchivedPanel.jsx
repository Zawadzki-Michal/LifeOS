export default function ArchivedPanel({ sessions, onRestore, onPurge, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="flex max-h-[80vh] w-full max-w-md flex-col rounded-2xl bg-white shadow-xl dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 p-4 dark:border-slate-700">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Archived conversations
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {sessions.length === 0 && (
            <p className="px-2 py-6 text-center text-sm text-slate-400">Nothing archived</p>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className="mb-1 flex items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              <span className="min-w-0 flex-1 truncate text-slate-700 dark:text-slate-300">
                {s.title || "New conversation"}
              </span>
              <div className="ml-2 flex shrink-0 gap-2">
                <button
                  onClick={() => onRestore(s.id)}
                  className="text-xs text-slate-500 hover:text-slate-900 dark:hover:text-slate-100"
                >
                  Restore
                </button>
                <button
                  onClick={() => {
                    if (confirm("Permanently delete this conversation? This can't be undone."))
                      onPurge(s.id);
                  }}
                  className="text-xs text-red-500 hover:text-red-700"
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
