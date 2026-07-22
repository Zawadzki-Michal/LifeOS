import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";

export default function ChatThread({ messages, pending }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      {messages.length === 0 && !pending && (
        <div className="flex h-full items-center justify-center text-center text-sm text-slate-400 dark:text-slate-500">
          Ask me anything — calendar, expenses, goals, health, whatever.
        </div>
      )}
      <div className="mx-auto flex max-w-3xl flex-col gap-3">
        {messages.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} />
        ))}
        {pending && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-slate-100 px-4 py-2.5 text-sm text-slate-400 dark:bg-slate-800 dark:text-slate-500">
              Thinking…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
