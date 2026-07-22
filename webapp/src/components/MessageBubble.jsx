import ReactMarkdown from "react-markdown";
import { canSpeak, speak } from "../tts.js";

export default function MessageBubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`group relative max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed sm:max-w-[75%] ${
          isUser
            ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
            : "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100"
        }`}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <>
            <div className="markdown-body">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
            {canSpeak() && (
              <button
                onClick={() => speak(content)}
                title="Read aloud"
                aria-label="Read this reply aloud"
                className="absolute -bottom-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-xs opacity-100 shadow-sm transition-opacity md:opacity-0 md:group-hover:opacity-100 dark:border-slate-700 dark:bg-slate-900"
              >
                🔊
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
