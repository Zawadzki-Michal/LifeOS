import { useEffect, useRef } from "react";

/**
 * Subscribes to /api/stream (SSE) for real-time scheduler messages (morning/
 * evening briefs, bill reminders) — see app/routers/stream.py. EventSource
 * reconnects automatically on drop, same-origin cookies are sent without
 * needing withCredentials. Only active once authed (`enabled`).
 *
 * `onEvent` is kept in a ref so the connection itself only opens/closes when
 * `enabled` changes — callers can pass a fresh closure every render without
 * the stream reconnecting on every state update.
 */
export function useChatStream(enabled, onEvent) {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled) return undefined;

    const source = new EventSource("/api/stream");
    source.onmessage = (e) => {
      try {
        onEventRef.current(JSON.parse(e.data));
      } catch {
        // ignore malformed events rather than crashing the stream
      }
    };
    return () => source.close();
  }, [enabled]);
}
