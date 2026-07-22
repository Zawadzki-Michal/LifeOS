import { useRef, useState } from "react";

// Formats picked in preference order — Safari (incl. iOS) doesn't support
// webm, only mp4/aac; Chrome/Firefox support webm/opus. Whisper on the
// backend decodes whichever one actually gets used, so it doesn't matter
// which — this just picks whatever the browser can actually record.
const CANDIDATE_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

function pickMimeType() {
  if (typeof MediaRecorder === "undefined") return null;
  return CANDIDATE_MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

export default function ChatInput({ onSend, onSendVoice, disabled }) {
  const [text, setText] = useState("");
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);

  function submit() {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  }

  async function startRecording() {
    setMicError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setMicError("This browser doesn't support microphone recording.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = pickMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        const blob = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });
        if (blob.size > 0) onSendVoice(blob);
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setMicError("Couldn't access the microphone — check permissions.");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  function toggleRecording() {
    if (disabled) return;
    if (recording) {
      stopRecording();
    } else {
      startRecording();
    }
  }

  return (
    <div className="border-t border-slate-200 p-3 dark:border-slate-800 sm:p-4">
      {micError && (
        <p className="mx-auto mb-2 max-w-3xl text-xs text-red-600 dark:text-red-400">
          {micError}
        </p>
      )}
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <button
          onClick={toggleRecording}
          disabled={disabled}
          title={recording ? "Stop recording" : "Record a voice message"}
          aria-label={recording ? "Stop recording" : "Record a voice message"}
          className={`flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-xl border text-lg disabled:opacity-40 ${
            recording
              ? "animate-pulse border-red-300 bg-red-500 text-white dark:border-red-700"
              : "border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          }`}
        >
          {recording ? "⏹" : "🎤"}
        </button>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder={recording ? "Recording…" : "Message LifeOS…"}
          disabled={recording}
          className="max-h-40 flex-1 resize-none rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-base text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:ring-slate-600 sm:text-sm"
        />
        <button
          onClick={submit}
          disabled={disabled || recording || !text.trim()}
          className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
        >
          Send
        </button>
      </div>
    </div>
  );
}
