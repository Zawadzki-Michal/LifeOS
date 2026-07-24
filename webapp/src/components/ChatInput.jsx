import { useRef, useState } from "react";
import { ArrowUp, Camera, Mic, Square } from "lucide-react";

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

export default function ChatInput({ value, onChange, onSend, onSendVoice, onSendImage, disabled }) {
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const imageInputRef = useRef(null);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    onChange("");
  }

  function handleImagePicked(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow picking the same file again later
    if (!file || disabled) return;
    onSendImage(file, value.trim() || null);
    onChange("");
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
    <div className="px-3 pt-2 sm:px-4" style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
      {micError && (
        <p className="mx-auto mb-2 max-w-3xl text-xs text-danger">{micError}</p>
      )}
      <div className="mx-auto flex max-w-3xl items-end gap-1.5 rounded-3xl border border-border bg-raised p-1.5">
        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          onChange={handleImagePicked}
          className="hidden"
        />
        <button
          onClick={() => imageInputRef.current?.click()}
          disabled={disabled || recording}
          title="Upload a screenshot or photo (e.g. Apple Health/Activity)"
          aria-label="Upload an image"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted hover:bg-surface hover:text-ink disabled:opacity-40 active:scale-95"
        >
          <Camera size={18} />
        </button>
        <button
          onClick={toggleRecording}
          disabled={disabled}
          title={recording ? "Stop recording" : "Record a voice message"}
          aria-label={recording ? "Stop recording" : "Record a voice message"}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full disabled:opacity-40 active:scale-95 ${
            recording ? "animate-pulse bg-danger text-white" : "text-muted hover:bg-surface hover:text-ink"
          }`}
        >
          {recording ? <Square size={16} /> : <Mic size={18} />}
        </button>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder={recording ? "Recording…" : "Message LifeOS…"}
          disabled={recording}
          className="max-h-40 flex-1 resize-none bg-transparent px-1 py-2 text-base text-ink placeholder:text-faint focus:outline-none disabled:opacity-60 sm:text-sm"
        />
        <button
          onClick={submit}
          disabled={disabled || recording || !value.trim()}
          aria-label="Send"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-white hover:bg-accent-strong disabled:opacity-40 active:scale-95"
        >
          <ArrowUp size={18} />
        </button>
      </div>
    </div>
  );
}
