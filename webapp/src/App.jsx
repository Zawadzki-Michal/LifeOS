import { useCallback, useEffect, useRef, useState } from "react";
import { Menu, Square } from "lucide-react";
import { api } from "./api.js";
import { isSpeaking, onSpeakingChange, speak, stopSpeaking } from "./tts.js";
import { useChatStream } from "./useChatStream.js";
import LoginScreen from "./components/LoginScreen.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ChatThread from "./components/ChatThread.jsx";
import ChatInput from "./components/ChatInput.jsx";
import ArchivedPanel from "./components/ArchivedPanel.jsx";
import UsagePanel from "./components/UsagePanel.jsx";

const VOICE_PLACEHOLDER = "🎤 …";
const IMAGE_PLACEHOLDER = "📷 …";

export default function App() {
  const [authState, setAuthState] = useState("checking"); // checking|authed|anon
  const [userEmail, setUserEmail] = useState(null);
  const [userName, setUserName] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [archivedOpen, setArchivedOpen] = useState(false);
  const [archivedSessions, setArchivedSessions] = useState([]);
  const [usageOpen, setUsageOpen] = useState(false);
  const [usageData, setUsageData] = useState(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [usageError, setUsageError] = useState(null);
  const [unreadSessionIds, setUnreadSessionIds] = useState(() => new Set());
  const [pendingStatus, setPendingStatus] = useState(null);
  const [draftText, setDraftText] = useState("");
  // Tracks the session id a send is in flight for — separate from activeId
  // because a brand-new session's id isn't known/set as active until after
  // creation, but status events for it start arriving from the backend
  // almost immediately (before setActiveId ever runs).
  const sendingSessionIdRef = useRef(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [speaking, setSpeakingState] = useState(isSpeaking);

  useEffect(() => onSpeakingChange(setSpeakingState), []);

  useEffect(() => {
    api
      .me()
      .then((me) => {
        setUserEmail(me.email);
        setUserName(me.name);
        setAuthState("authed");
      })
      .catch(() => setAuthState("anon"));
  }, []);

  const refreshSessions = useCallback(async () => {
    const list = await api.listSessions();
    setSessions(list);
    return list;
  }, []);

  useEffect(() => {
    if (authState === "authed") refreshSessions().catch((e) => setError(e.message));
  }, [authState, refreshSessions]);

  useEffect(() => {
    setPendingStatus(null);
    if (activeId == null) {
      setMessages([]);
      return;
    }
    api.listMessages(activeId).then(setMessages).catch((e) => setError(e.message));
  }, [activeId]);

  useChatStream(authState === "authed", (event) => {
    if (event.status) {
      if (event.session_id === activeId || event.session_id === sendingSessionIdRef.current) {
        setPendingStatus(event.status);
      }
      return;
    }
    const { session_id: sessionId, message } = event;
    if (sessionId === activeId) {
      setMessages((prev) =>
        prev.some((m) => m.id === message.id) ? prev : [...prev, message]
      );
    } else {
      setUnreadSessionIds((prev) => new Set(prev).add(sessionId));
    }
    refreshSessions().catch(() => {});
  });

  function handleNew() {
    setActiveId(null);
    setMessages([]);
    setSidebarOpen(false);
  }

  function handleSelect(id) {
    setActiveId(id);
    setSidebarOpen(false);
    setUnreadSessionIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }

  async function handleSend(text) {
    setError(null);
    setPending(true);
    setPendingStatus(null);
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content: text }]);
    try {
      // Resolve the session id but don't setActiveId yet — that would fire
      // the activeId-watching effect below mid-flight and clobber this
      // optimistic message with an empty fetch before the reply lands.
      let sessionId = activeId;
      if (sessionId == null) {
        const created = await api.createSession();
        sessionId = created.id;
      }
      sendingSessionIdRef.current = sessionId;
      await api.sendMessage(sessionId, text);
      const [freshMessages] = await Promise.all([api.listMessages(sessionId), refreshSessions()]);
      setActiveId(sessionId);
      setMessages(freshMessages);
    } catch (e) {
      setError(e.message);
    } finally {
      sendingSessionIdRef.current = null;
      setPending(false);
      setPendingStatus(null);
    }
  }

  async function handleSendVoice(blob) {
    setError(null);
    setPending(true);
    setPendingStatus("transcribing");
    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: "user", content: VOICE_PLACEHOLDER },
    ]);
    try {
      let sessionId = activeId;
      if (sessionId == null) {
        const created = await api.createSession();
        sessionId = created.id;
      }
      sendingSessionIdRef.current = sessionId;
      const { reply } = await api.sendVoiceMessage(sessionId, blob);
      const [freshMessages] = await Promise.all([api.listMessages(sessionId), refreshSessions()]);
      setActiveId(sessionId);
      setMessages(freshMessages);
      speak(reply);
    } catch (e) {
      setError(e.message);
      setMessages((prev) => prev.filter((m) => m.content !== VOICE_PLACEHOLDER));
    } finally {
      sendingSessionIdRef.current = null;
      setPending(false);
      setPendingStatus(null);
    }
  }

  async function handleSendImage(file, caption) {
    setError(null);
    setPending(true);
    setPendingStatus("analyzing_image");
    setMessages((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}`,
        role: "user",
        content: caption ? `📷 ${caption}` : IMAGE_PLACEHOLDER,
      },
    ]);
    try {
      let sessionId = activeId;
      if (sessionId == null) {
        const created = await api.createSession();
        sessionId = created.id;
      }
      sendingSessionIdRef.current = sessionId;
      await api.sendImageMessage(sessionId, file, caption);
      const [freshMessages] = await Promise.all([api.listMessages(sessionId), refreshSessions()]);
      setActiveId(sessionId);
      setMessages(freshMessages);
    } catch (e) {
      setError(e.message);
      setMessages((prev) =>
        prev.filter((m) => m.content !== IMAGE_PLACEHOLDER && m.content !== `📷 ${caption}`)
      );
    } finally {
      sendingSessionIdRef.current = null;
      setPending(false);
      setPendingStatus(null);
    }
  }

  async function handleRename(id, title) {
    await api.updateSession(id, { title });
    refreshSessions();
  }

  async function handleArchive(id) {
    await api.updateSession(id, { archived: true });
    if (id === activeId) {
      setActiveId(null);
      setMessages([]);
    }
    refreshSessions();
  }

  async function loadArchived() {
    const all = await api.listSessions(true);
    setArchivedSessions(all.filter((s) => s.archived));
  }

  async function handleShowArchived() {
    await loadArchived().catch((e) => setError(e.message));
    setArchivedOpen(true);
  }

  async function handleRestore(id) {
    await api.updateSession(id, { archived: false });
    await Promise.all([loadArchived(), refreshSessions()]);
  }

  async function handlePurge(id) {
    await api.deleteSession(id);
    await loadArchived();
  }

  async function handleLogout() {
    await api.logout();
    setAuthState("anon");
  }

  async function handleShowUsage() {
    setUsageOpen(true);
    setUsageLoading(true);
    setUsageError(null);
    try {
      setUsageData(await api.getOpenRouterUsage());
    } catch (e) {
      setUsageError(e.message);
    } finally {
      setUsageLoading(false);
    }
  }

  if (authState === "checking") {
    return (
      <div className="flex h-dvh items-center justify-center bg-bg text-sm text-faint">
        Loading…
      </div>
    );
  }
  if (authState === "anon") {
    return <LoginScreen />;
  }

  return (
    <div className="flex h-dvh bg-bg">
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
        />
      )}
      <div
        className={`fixed inset-y-0 left-0 z-40 w-72 transform transition-transform duration-200 md:relative md:z-auto md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ paddingLeft: "env(safe-area-inset-left)" }}
      >
        <Sidebar
          sessions={sessions}
          activeId={activeId}
          unreadSessionIds={unreadSessionIds}
          onSelect={handleSelect}
          onNew={handleNew}
          onRename={handleRename}
          onArchive={handleArchive}
          onLogout={handleLogout}
          onShowArchived={handleShowArchived}
          onShowUsage={handleShowUsage}
          userEmail={userEmail}
        />
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div
          className="flex items-center gap-3 border-b border-border p-3 md:hidden"
          style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}
        >
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-ink"
            aria-label="Open conversations"
          >
            <Menu size={22} />
          </button>
          <span className="text-sm font-semibold text-ink">LifeOS</span>
        </div>
        {error && (
          <div className="border-b border-danger/30 bg-danger-bg px-4 py-2 text-sm text-danger">
            {error}
          </div>
        )}
        <ChatThread
          messages={messages}
          pending={pending}
          pendingStatus={pendingStatus}
          onPromptSelect={setDraftText}
          userName={userName}
        />
        {speaking && (
          <div className="flex justify-center bg-bg pt-2">
            <button
              onClick={stopSpeaking}
              className="mb-1 flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-ink hover:bg-raised"
            >
              <Square size={12} /> Stop reading
            </button>
          </div>
        )}
        <ChatInput
          value={draftText}
          onChange={setDraftText}
          onSend={handleSend}
          onSendVoice={handleSendVoice}
          onSendImage={handleSendImage}
          disabled={pending}
        />
      </div>
      {archivedOpen && (
        <ArchivedPanel
          sessions={archivedSessions}
          onRestore={handleRestore}
          onPurge={handlePurge}
          onClose={() => setArchivedOpen(false)}
        />
      )}
      {usageOpen && (
        <UsagePanel
          data={usageData}
          loading={usageLoading}
          error={usageError}
          onClose={() => setUsageOpen(false)}
        />
      )}
    </div>
  );
}
