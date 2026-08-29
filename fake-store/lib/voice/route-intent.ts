import {
  classifyIntentLocally,
  defaultIntentFallback,
} from "@/lib/voice/intent";
import type {
  ClassifyIntentResponse,
  RunStatusForVoice,
  VoiceIntent,
} from "@/lib/voice/types";

const VOICE_INTENT_API_URL =
  process.env.NEXT_PUBLIC_AGENT_HTTP_URL?.trim() ||
  "http://127.0.0.1:8765/voice/classify-intent";

export interface RoutedVoiceIntent {
  intent: VoiceIntent;
  taskText: string;
}

async function classifyViaBackend(
  text: string,
  runStatus: RunStatusForVoice,
): Promise<ClassifyIntentResponse | null> {
  try {
    const response = await fetch(VOICE_INTENT_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, runStatus }),
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as ClassifyIntentResponse;
  } catch {
    return null;
  }
}

export async function routeVoiceIntent(
  text: string,
  runStatus: RunStatusForVoice,
): Promise<RoutedVoiceIntent> {
  const trimmed = text.trim();
  const local = classifyIntentLocally(trimmed, runStatus);

  if (local) {
    return { intent: local, taskText: trimmed };
  }

  if (runStatus === "waiting_for_user") {
    const remote = await classifyViaBackend(trimmed, runStatus);
    if (remote) {
      return {
        intent: remote.intent,
        taskText: remote.taskText.trim() || trimmed,
      };
    }
  }

  const fallback = defaultIntentFallback(trimmed, runStatus);
  return { intent: fallback, taskText: trimmed };
}
