export type RunStatusForVoice = "idle" | "active" | "waiting_for_user";

export type VoiceIntent = "resume" | "new_task";

export type VoiceUiState =
  | "idle"
  | "recording"
  | "transcribing"
  | "routing"
  | "error";

export interface ClassifyIntentResponse {
  intent: VoiceIntent;
  taskText: string;
}
