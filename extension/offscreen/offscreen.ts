import {
  isMoonshineRecording,
  startMoonshinePtt,
  stopMoonshinePtt,
} from "../voice/moonshine-transcriber";
import type {
  VoicePttStartMessage,
  VoicePttStopMessage,
  VoiceSource,
  VoiceStatusMessage,
  VoiceTranscriptMessage,
} from "../shared/voice/types";

const OFFSCREEN_TARGET = "offscreen";

function broadcast(message: VoiceStatusMessage | VoiceTranscriptMessage): void {
  void chrome.runtime.sendMessage(message);
}

function status(
  state: VoiceStatusMessage["state"],
  source: VoiceSource,
  text?: string,
  errorCode?: VoiceStatusMessage["errorCode"],
): void {
  broadcast({ type: "VOICE_STATUS", state, text, errorCode, source });
}

function transcript(
  text: string,
  phase: VoiceTranscriptMessage["phase"],
  source: VoiceSource,
): void {
  broadcast({ type: "VOICE_TRANSCRIPT", text, phase, source });
}

let activeSource: VoiceSource | null = null;

chrome.runtime.onMessage.addListener((message: unknown) => {
  if (!message || typeof message !== "object") {
    return;
  }

  const payload = message as { type?: string; target?: string };
  if (payload.target !== OFFSCREEN_TARGET) {
    return;
  }

  if (payload.type === "VOICE_PTT_START") {
    const { source } = message as VoicePttStartMessage;
    void handlePttStart(source);
    return;
  }

  if (payload.type === "VOICE_PTT_STOP") {
    const { source } = message as VoicePttStopMessage;
    void handlePttStop(source);
  }
});

async function handlePttStart(source: VoiceSource): Promise<void> {
  if (isMoonshineRecording()) {
    return;
  }

  activeSource = source;
  status("loading_model", source, "Loading speech model…");

  try {
    await startMoonshinePtt({
      onModelLoading: () => status("loading_model", source, "Loading speech model…"),
      onRecording: () => status("recording", source, "Listening…"),
      onPartial: (text) => {
        if (text.trim()) {
          transcript(text, "partial", source);
          status("recording", source, text);
        }
      },
      onError: (code, message) => {
        activeSource = null;
        status("error", source, message, code);
      },
    });
  } catch (error) {
    activeSource = null;
    status(
      "error",
      source,
      error instanceof Error ? error.message : "Voice capture failed.",
      "transcription_failed",
    );
  }
}

async function handlePttStop(source: VoiceSource): Promise<void> {
  if (activeSource !== source && activeSource !== null) {
    return;
  }

  status("transcribing", source, "Transcribing…");

  const finalText = await stopMoonshinePtt();
  activeSource = null;

  if (!finalText) {
    status("error", source, "No speech detected.", "no_speech");
    return;
  }

  transcript(finalText, "final", source);
  status("idle", source, finalText);
}
