// Browser-native speech synthesis — no backend involved, runs entirely
// on-device (works in iOS Safari, unlike the SpeechRecognition API).
//
// Replies are Polish by default (app/prompts.py instructs the model to
// reply in Polish regardless of input language — this household
// communicates in Polish), but speechSynthesis defaults to whatever
// voice/language the device happens to be set to. Force a Polish voice
// explicitly instead of trusting the default.

export function canSpeak() {
  return "speechSynthesis" in window;
}

// Tiny pub-sub so any component (the stop button, a "speaking" indicator)
// can react to playback state without prop-drilling through every place
// that calls speak() — the reply bubble replay button and the voice-message
// auto-play in App.jsx both trigger speech independently.
const speakingListeners = new Set();
let speaking = false;

function setSpeaking(value) {
  speaking = value;
  speakingListeners.forEach((cb) => cb(speaking));
}

export function isSpeaking() {
  return speaking;
}

export function onSpeakingChange(callback) {
  speakingListeners.add(callback);
  return () => speakingListeners.delete(callback);
}

function getVoices() {
  return new Promise((resolve) => {
    const existing = window.speechSynthesis.getVoices();
    if (existing.length > 0) {
      resolve(existing);
      return;
    }
    // Voice list often loads asynchronously (esp. Chrome) — nothing is
    // available until this fires once.
    window.speechSynthesis.onvoiceschanged = () => {
      resolve(window.speechSynthesis.getVoices());
    };
    setTimeout(() => resolve(window.speechSynthesis.getVoices()), 500);
  });
}

export async function speak(text) {
  if (!canSpeak() || !text) return;
  window.speechSynthesis.cancel(); // don't overlap with any prior utterance

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "pl-PL";
  utterance.onstart = () => setSpeaking(true);
  utterance.onend = () => setSpeaking(false);
  utterance.onerror = () => setSpeaking(false);

  const voices = await getVoices();
  const plVoice =
    voices.find((v) => v.lang === "pl-PL") || voices.find((v) => v.lang.startsWith("pl"));
  if (plVoice) utterance.voice = plVoice;

  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking() {
  if (!canSpeak()) return;
  window.speechSynthesis.cancel(); // doesn't reliably fire onend in every browser
  setSpeaking(false);
}
