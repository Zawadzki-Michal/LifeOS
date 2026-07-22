// Browser-native speech synthesis — no backend involved, runs entirely
// on-device (works in iOS Safari, unlike the SpeechRecognition API).

export function canSpeak() {
  return "speechSynthesis" in window;
}

export function speak(text) {
  if (!canSpeak() || !text) return;
  window.speechSynthesis.cancel(); // don't overlap with any prior utterance
  const utterance = new SpeechSynthesisUtterance(text);
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking() {
  if (canSpeak()) window.speechSynthesis.cancel();
}
