// Browser-native speech synthesis — no backend involved, runs entirely
// on-device (works in iOS Safari, unlike the SpeechRecognition API).
//
// Replies are always in English (the whole persona/system prompt is
// English), but speechSynthesis defaults to whatever voice/language the
// device is set to — on a Polish device that's a Polish voice reading
// English text with Polish phonetics. Force an English voice explicitly
// instead of trusting the default.

export function canSpeak() {
  return "speechSynthesis" in window;
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
  utterance.lang = "en-US";

  const voices = await getVoices();
  const enVoice =
    voices.find((v) => v.lang === "en-US") || voices.find((v) => v.lang.startsWith("en"));
  if (enVoice) utterance.voice = enVoice;

  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking() {
  if (canSpeak()) window.speechSynthesis.cancel();
}
