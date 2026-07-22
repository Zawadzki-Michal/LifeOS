import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import { speak } from "./tts.js";
import LoginScreen from "./components/LoginScreen.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ChatThread from "./components/ChatThread.jsx";
import ChatInput from "./components/ChatInput.jsx";
import ArchivedPanel from "./components/ArchivedPanel.jsx";

const VOICE_PLACEHOLDER = "🎤 …";

export default function App() {
  const [authState, setAuthState] = useState("checking"); // checking|authed|anon
  const [userEmail, setUserEmail] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [archivedOpen, setArchivedOpen] = useState(false);
  const [archivedSessions, setArchivedSessions] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useState(() => {
    const stored = localStorage.getItem("lifeos-theme");
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("lifeos-theme", theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  useEffect(() => {
    api
      .me()
      .then((me) => {
        setUserEmail(me.email);
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
    if (activeId == null) {
      setMessages([]);
      return;
    }
    api.listMessages(activeId).then(setMessages).catch((e) => setError(e.message));
  }, [activeId]);

  function handleNew() {
    setActiveId(null);
    setMessages([]);
    setSidebarOpen(false);
  }

  function handleSelect(id) {
    setActiveId(id);
    setSidebarOpen(false);
  }

  async function handleSend(text) {
    setError(null);
    setPending(true);
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
      await api.sendMessage(sessionId, text);
      const [freshMessages] = await Promise.all([api.listMessages(sessionId), refreshSessions()]);
      setActiveId(sessionId);
      setMessages(freshMessages);
    } catch (e) {
      setError(e.message);
    } finally {
      setPending(false);
    }
  }

  async function handleSendVoice(blob) {
    setError(null);
    setPending(true);
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
      const { reply } = await api.sendVoiceMessage(sessionId, blob);
      const [freshMessages] = await Promise.all([api.listMessages(sessionId), refreshSessions()]);
      setActiveId(sessionId);
      setMessages(freshMessages);
      speak(reply);
    } catch (e) {
      setError(e.message);
      setMessages((prev) => prev.filter((m) => m.content !== VOICE_PLACEHOLDER));
    } finally {
      setPending(false);
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

  if (authState === "checking") {
    return (
      <div className="flex h-screen items-center justify-center bg-white text-sm text-slate-400 dark:bg-slate-950 dark:text-slate-500">
        Loading…
      </div>
    );
  }
  if (authState === "anon") {
    return <LoginScreen />;
  }

  return (
    <div className="flex h-screen bg-white dark:bg-slate-950">
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
        />
      )}
      <div
        className={`fixed inset-y-0 left-0 z-40 w-72 transform transition-transform duration-200 md:relative md:z-auto md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar
          sessions={sessions}
          activeId={activeId}
          onSelect={handleSelect}
          onNew={handleNew}
          onRename={handleRename}
          onArchive={handleArchive}
          onLogout={handleLogout}
          onShowArchived={handleShowArchived}
          userEmail={userEmail}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-slate-200 p-3 dark:border-slate-800 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-xl leading-none text-slate-600 dark:text-slate-300"
            aria-label="Open conversations"
          >
            ☰
          </button>
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">LifeOS</span>
        </div>
        {error && (
          <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}
        <ChatThread messages={messages} pending={pending} />
        <ChatInput onSend={handleSend} onSendVoice={handleSendVoice} disabled={pending} />
      </div>
      {archivedOpen && (
        <ArchivedPanel
          sessions={archivedSessions}
          onRestore={handleRestore}
          onPurge={handlePurge}
          onClose={() => setArchivedOpen(false)}
        />
      )}
    </div>
  );
}
