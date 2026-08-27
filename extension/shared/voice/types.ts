export type VoiceSource = "popup" | "overlay";

export type RunStatusForVoice = "idle" | "active" | "waiting_for_user";

export type VoiceIntent = "resume" | "new_task";

export type VoiceUiState =
  | "idle"
  | "loading_model"
  | "recording"
  | "transcribing"
  | "routing"
  | "error";

export type VoiceErrorCode =
  | "disabled"
  | "mic_denied"
  | "no_speech"
  | "transcription_failed"
  | "intent_failed"
  | "backend_unreachable"
  | "no_run_to_resume";

export interface VoiceStatusMessage {
  type: "VOICE_STATUS";
  state: VoiceUiState;
  text?: string;
  errorCode?: VoiceErrorCode;
  source?: VoiceSource;
}

export interface VoiceTranscriptMessage {
  type: "VOICE_TRANSCRIPT";
  text: string;
  phase: "partial" | "final";
  source: VoiceSource;
}

export interface VoicePttStartMessage {
  type: "VOICE_PTT_START";
  source: VoiceSource;
}

export interface VoicePttStopMessage {
  type: "VOICE_PTT_STOP";
  source: VoiceSource;
}

export interface VoiceGetConfigMessage {
  type: "GET_VOICE_CONFIG";
}

export interface VoiceConfigResponse {
  type: "VOICE_CONFIG";
  enabled: boolean;
}

export type VoiceClientMessage =
  | VoicePttStartMessage
  | VoicePttStopMessage
  | VoiceGetConfigMessage;

export type VoiceBroadcastMessage =
  | VoiceStatusMessage
  | VoiceTranscriptMessage
  | VoiceConfigResponse;

export interface ClassifyIntentRequest {
  text: string;
  runStatus: RunStatusForVoice;
}

export interface ClassifyIntentResponse {
  intent: VoiceIntent;
  taskText: string;
}
