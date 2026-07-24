const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 401) {
    const err = new Error("unauthorized");
    err.status = 401;
    throw err;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function requestMultipart(path, form) {
  // No Content-Type here — the browser sets the multipart boundary itself.
  const res = await fetch(BASE + path, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (res.status === 401) {
    const err = new Error("unauthorized");
    err.status = 401;
    throw err;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  me: () => request("/auth/me"),
  logout: () => request("/auth/logout", { method: "POST" }),
  listSessions: (includeArchived) =>
    request(`/sessions${includeArchived ? "?include_archived=true" : ""}`),
  createSession: (title) =>
    request("/sessions", {
      method: "POST",
      body: JSON.stringify(title ? { title } : {}),
    }),
  updateSession: (id, patch) =>
    request(`/sessions/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteSession: (id) => request(`/sessions/${id}`, { method: "DELETE" }),
  listMessages: (id) => request(`/sessions/${id}/messages`),
  sendMessage: (id, text) =>
    request(`/sessions/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  sendVoiceMessage: (id, blob) => {
    const form = new FormData();
    form.append("file", blob, "voice.webm");
    return requestMultipart(`/sessions/${id}/voice-messages`, form);
  },
  sendImageMessage: (id, file, caption) => {
    const form = new FormData();
    form.append("file", file, file.name || "image.jpg");
    if (caption) form.append("caption", caption);
    return requestMultipart(`/sessions/${id}/image-messages`, form);
  },
  getOpenRouterUsage: () => request("/usage/openrouter"),
};
