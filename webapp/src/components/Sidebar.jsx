import { useEffect, useRef, useState } from "react";
import { Archive, BarChart3, CalendarDays, LogOut, MoreVertical, Pencil, Plus, Trash2 } from "lucide-react";

function formatTime(iso) {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function dayDiff(iso) {
  const d = new Date(iso);
  const now = new Date();
  const startOfDay = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());
  return Math.round((startOfDay(now) - startOfDay(d)) / 86400000);
}

function groupLabel(iso) {
  const diff = dayDiff(iso);
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff <= 7) return "Last 7 days";
  return "Older";
}

const GROUP_ORDER = ["Today", "Yesterday", "Last 7 days", "Older"];

function groupSessions(sessions) {
  const groups = new Map();
  for (const s of sessions) {
    const label = groupLabel(s.updated_at);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(s);
  }
  return GROUP_ORDER.filter((label) => groups.has(label)).map((label) => [label, groups.get(label)]);
}

export default function Sidebar({
  sessions,
  activeId,
  unreadSessionIds,
  onSelect,
  onNew,
  onRename,
  onArchive,
  onLogout,
  onShowArchived,
  onShowUsage,
  userEmail,
}) {
  const [editingId, setEditingId] = useState(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [menuOpenId, setMenuOpenId] = useState(null);
  const menuRef = useRef(null);

  useEffect(() => {
    if (menuOpenId == null) return;
    function onDocClick(e) {
      if (!menuRef.current?.contains(e.target)) setMenuOpenId(null);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [menuOpenId]);

  function startEdit(session) {
    setEditingId(session.id);
    setDraftTitle(session.title || "");
    setMenuOpenId(null);
  }

  function commitEdit(id) {
    const title = draftTitle.trim();
    if (title) onRename(id, title);
    setEditingId(null);
  }

  const grouped = groupSessions(sessions);

  return (
    <div className="flex h-full w-72 flex-col border-r border-border bg-surface">
      <div className="p-3">
        <button
          onClick={onNew}
          className="flex w-full items-center justify-center gap-1.5 rounded-full bg-accent px-3 py-2.5 text-sm font-medium text-white hover:bg-accent-strong"
        >
          <Plus size={16} /> New chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2">
        {sessions.length === 0 && (
          <p className="px-2 py-4 text-center text-sm text-faint">No conversations yet</p>
        )}
        {grouped.map(([label, group]) => (
          <div key={label} className="mb-2">
            <p className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-faint">
              {label}
            </p>
            {group.map((s) => (
              <div
                key={s.id}
                onClick={() => onSelect(s.id)}
                className={`group relative mb-1 flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm ${
                  s.id === activeId
                    ? "border-l-2 border-accent bg-raised text-ink"
                    : "border-l-2 border-transparent text-muted hover:bg-raised"
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
                    className="w-full rounded border border-border-strong bg-raised px-1 py-0.5 text-base text-ink sm:text-sm"
                  />
                ) : (
                  <>
                    <span className="flex min-w-0 flex-col">
                      <span className="flex items-center gap-1.5 truncate">
                        {s.is_scheduler && (
                          <CalendarDays size={13} className="shrink-0 text-faint" title="Proactive daily briefings" />
                        )}
                        {unreadSessionIds?.has(s.id) && (
                          <span className="h-2 w-2 shrink-0 rounded-full bg-accent" title="New message" />
                        )}
                        <span className="truncate">{s.title || "New conversation"}</span>
                      </span>
                      <span className="text-xs text-faint">{formatTime(s.updated_at)}</span>
                    </span>
                    <div className="relative ml-2 shrink-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpenId(menuOpenId === s.id ? null : s.id);
                        }}
                        aria-label="Conversation options"
                        className="rounded p-1 text-faint opacity-100 hover:bg-border hover:text-ink md:opacity-0 md:group-hover:opacity-100"
                      >
                        <MoreVertical size={16} />
                      </button>
                      {menuOpenId === s.id && (
                        <div
                          ref={menuRef}
                          onClick={(e) => e.stopPropagation()}
                          className="absolute right-0 top-full z-10 mt-1 w-36 overflow-hidden rounded-lg border border-border bg-raised py-1 shadow-lg"
                        >
                          <button
                            onClick={() => startEdit(s)}
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-ink hover:bg-surface"
                          >
                            <Pencil size={14} /> Rename
                          </button>
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              onArchive(s.id);
                            }}
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-danger hover:bg-surface"
                          >
                            <Trash2 size={14} /> Archive
                          </button>
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="border-t border-border p-3">
        <p className="mb-2 truncate text-xs text-faint">{userEmail}</p>
        <div className="flex items-center gap-1">
          <button
            onClick={onLogout}
            title="Sign out"
            aria-label="Sign out"
            className="rounded-lg p-2 text-muted hover:bg-raised hover:text-ink"
          >
            <LogOut size={17} />
          </button>
          <button
            onClick={onShowArchived}
            title="Archived"
            aria-label="Archived conversations"
            className="rounded-lg p-2 text-muted hover:bg-raised hover:text-ink"
          >
            <Archive size={17} />
          </button>
          <button
            onClick={onShowUsage}
            title="OpenRouter usage"
            aria-label="OpenRouter usage"
            className="rounded-lg p-2 text-muted hover:bg-raised hover:text-ink"
          >
            <BarChart3 size={17} />
          </button>
        </div>
      </div>
    </div>
  );
}
