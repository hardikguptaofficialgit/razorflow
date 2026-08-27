import { VOICE_INTENT_API_URL } from "../shared/voice/config";
import {
  classifyIntentLocally,
  defaultIntentFallback,
} from "../shared/voice/intent";
import type {
  ClassifyIntentResponse,
  RunStatusForVoice,
  VoiceIntent,
} from "../shared/voice/types";

export interface RoutedVoiceIntent {
  intent: VoiceIntent;
  taskText: string;
  usedGroq: boolean;
}

async function classifyViaGroq(
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
    return {
      intent: local,
      taskText: local === "new_task" ? trimmed : trimmed,
      usedGroq: false,
    };
  }

  if (runStatus === "waiting_for_user") {
    const groq = await classifyViaGroq(trimmed, runStatus);
    if (groq) {
      return {
        intent: groq.intent,
        taskText: groq.taskText.trim() || trimmed,
        usedGroq: true,
      };
    }
  }

  const fallback = defaultIntentFallback(trimmed, runStatus);
  return {
    intent: fallback,
    taskText: trimmed,
    usedGroq: false,
  };
}
