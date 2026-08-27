import type { RunStatusForVoice, VoiceIntent } from "./types";

const RESUME_EXACT = new Set([
  "continue",
  "resume",
  "done",
  "go ahead",
  "proceed",
  "i'm done",
  "im done",
  "finished",
  "all set",
  "ready",
  "that's done",
  "thats done",
  "keep going",
]);

const RESUME_PREFIX =
  /^(please\s+)?(continue|resume|go ahead|proceed)(\s+please)?[.!]?$/i;

const RESUME_SHORT =
  /^(i'?m\s+)?(done|finished|ready|logged in|signed in)[.!]?$/i;

export function classifyIntentLocally(
  text: string,
  runStatus: RunStatusForVoice,
): VoiceIntent | null {
  const normalized = text.trim().toLowerCase().replace(/\s+/g, " ");
  if (!normalized) {
    return null;
  }

  if (runStatus !== "waiting_for_user") {
    return "new_task";
  }

  if (RESUME_EXACT.has(normalized)) {
    return "resume";
  }

  if (RESUME_PREFIX.test(normalized) || RESUME_SHORT.test(normalized)) {
    return "resume";
  }

  const words = normalized.split(" ");
  if (words.length <= 4 && RESUME_EXACT.has(words[0] ?? "")) {
    return "resume";
  }

  if (words.length >= 5) {
    return "new_task";
  }

  if (
    words.length >= 3 &&
    !RESUME_EXACT.has(words[0] ?? "") &&
    !normalized.includes("continue") &&
    !normalized.includes("resume")
  ) {
    return "new_task";
  }

  return null;
}

export function defaultIntentFallback(
  text: string,
  runStatus: RunStatusForVoice,
): VoiceIntent {
  if (runStatus === "waiting_for_user" && text.trim().split(/\s+/).length <= 3) {
    return "resume";
  }

  return "new_task";
}
