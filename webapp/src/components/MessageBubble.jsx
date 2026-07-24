import ReactMarkdown from "react-markdown";
import { Cloud, Cpu, Image as ImageIcon, Volume2 } from "lucide-react";
import { canSpeak, speak } from "../tts.js";

// Which model actually produced this reply (app/chat_service.py /
// app/routers/sessions.py persist chat_message.model) — labeled so it's
// visible at a glance whether an answer came from the local model or a
// cloud hand-off, after repeated confusion about which one responded.
function modelInfo(model) {
  if (!model) return null;
  if (model.startsWith("anthropic/")) return { label: "Sonnet", Icon: Cloud };
  if (model.startsWith("google/")) return { label: "Gemini", Icon: ImageIcon };
  return { label: "Local (Qwen)", Icon: Cpu };
}

export default function MessageBubble({ role, content, model }) {
  const isUser = role === "user";
  const info = !isUser ? modelInfo(model) : null;
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`group relative max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed sm:max-w-[75%] ${
          isUser ? "bg-accent text-white" : "bg-surface text-ink"
        }`}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <>
            <div className="markdown-body">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
            {info && (
              <div className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-raised px-2 py-0.5 text-[10px] font-medium text-faint">
                <info.Icon size={11} /> {info.label}
              </div>
            )}
            {canSpeak() && (
              <button
                onClick={() => speak(content)}
                title="Read aloud"
                aria-label="Read this reply aloud"
                className="absolute -bottom-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-raised text-faint opacity-100 shadow-sm transition-opacity hover:text-ink md:opacity-0 md:group-hover:opacity-100"
              >
                <Volume2 size={12} />
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
