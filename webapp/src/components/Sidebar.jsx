import { useState } from "react";

function formatTime(iso) {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function Sidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
  onRename,
  onArchive,
  onLogout,
  onShowArchived,
  userEmail,
  theme,
  onToggleTheme,
}) {
  const [editingId, setEditingId] = useState(null);
  const [draftTitle, setDraftTitle] = useState("");

  function startEdit(session) {
    setEditingId(session.id);
    setDraftTitle(session.title || "");
  }

  function commitEdit(id) {
    const title = draftTitle.trim();
    if (title) onRename(id, title);
    setEditingId(null);
  }

  return (
    <div className="flex h-full w-72 flex-col border-r border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
        >
          + New chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2">
        {sessions.length === 0 && (
          <p className="px-2 py-4 text-center text-sm text-slate-400 dark:text-slate-500">
            No conversations yet
          </p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`group mb-1 flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm ${
              s.id === activeId
                ? "bg-slate-200 text-slate-900 dark:bg-slate-700 dark:text-slate-100"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {editingId === s.id ? (
              <input
                autoFocus
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                onBlur={() => commitEdit(s.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitEdit(s.id);
                  if (e.key === "Escape") setEditingId(null);
                }}
                onClick={(e) => e.stopPropagation()}
                className="w-full rounded border border-slate-300 px-1 py-0.5 text-base dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 sm:text-sm"
              />
            ) : (
              <>
                <span className="flex min-w-0 flex-col">
                  <span className="truncate">{s.title || "New conversation"}</span>
                  <span className="text-xs text-slate-400 dark:text-slate-500">
                    {formatTime(s.updated_at)}
                  </span>
                </span>
                {/* Always visible on mobile (no hover there); hover-reveal only from md up. */}
                <span className="ml-2 flex shrink-0 gap-1 md:hidden md:group-hover:flex">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startEdit(s);
                    }}
                    className="rounded px-1 text-xs text-slate-400 hover:text-slate-700 dark:text-slate-500 dark:hover:text-slate-200"
                    title="Rename"
                  >
                    ✎
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onArchive(s.id);
                    }}
                    className="rounded px-1 text-xs text-slate-400 hover:text-red-600 dark:text-slate-500 dark:hover:text-red-400"
                    title="Archive (recoverable — see Archived below)"
                  >
                    ✕
                  </button>
                </span>
              </>
            )}
          </div>
        ))}
      </div>
      <div className="border-t border-slate-200 p-3 dark:border-slate-800">
        <p className="mb-2 truncate text-xs text-slate-400 dark:text-slate-500">{userEmail}</p>
        <div className="flex items-center gap-3">
          <button
            onClick={onLogout}
            className="text-xs text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100"
          >
            Sign out
          </button>
          <button
            onClick={onShowArchived}
            className="text-xs text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100"
          >
            Archived
          </button>
          <button
            onClick={onToggleTheme}
            className="ml-auto text-xs text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100"
            title="Toggle theme"
          >
            {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
          </button>
        </div>
      </div>
    </div>
  );
}
