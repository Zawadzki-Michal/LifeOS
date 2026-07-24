import { useEffect, useRef } from "react";
import { Sparkles } from "lucide-react";
import MessageBubble from "./MessageBubble.jsx";

// Live "what's happening" labels pushed over SSE (app/redis_client.py's
// publish_status_event, see app/chat_service.py and app/tools.py) so a slow
// local-model reply doesn't look like the app just hung.
const STATUS_LABELS = {
  transcribing: "Transcribing…",
  thinking_local: "Thinking (local model)…",
  thinking_cloud: "Asking the cloud model…",
  analyzing_image: "Analyzing image…",
};

const SUGGESTED_PROMPTS = [
  "What's on my calendar today?",
  "Log a meal",
  "How much did I spend this month?",
  "Give me health advice",
];

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function TypingDots() {
  return (
    <span className="flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-faint"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

export default function ChatThread({ messages, pending, pendingStatus, onPromptSelect, userName }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending, pendingStatus]);

  if (messages.length === 0 && !pending) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-6 overflow-y-auto px-6 py-4 text-center">
        <div>
          <div className="relative mx-auto mb-3 flex h-9 w-9 items-center justify-center">
            <div className="absolute h-16 w-16 rounded-full bg-accent/20 blur-xl" />
            <Sparkles className="relative text-accent" size={26} />
          </div>
          <p className="text-sm text-muted">
            {greeting()}
            {userName && (
              <>
                , <span className="font-medium text-accent">{userName}</span>
              </>
            )}
          </p>
          <h1 className="mt-1 text-3xl font-semibold text-ink">How can I help you?</h1>
        </div>
        <div className="flex max-w-md flex-wrap justify-center gap-2">
          {SUGGESTED_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => onPromptSelect?.(prompt)}
              className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-sm text-muted hover:border-border-strong hover:text-ink"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-3">
        {messages.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} model={m.model} />
        ))}
        {pending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-surface px-4 py-2.5 text-sm text-faint">
              <TypingDots />
              <span>{STATUS_LABELS[pendingStatus] || "Thinking…"}</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
