import {
  MicrophoneTranscriber,
  MoonshineError,
  type TranscriberCallbacks,
} from "@moonshine-ai/moonshine-js";
import { MOONSHINE_MODEL_PATH } from "../shared/voice/config";
import type { VoiceErrorCode } from "../shared/voice/types";

export interface MoonshinePttCallbacks {
  onPartial: (text: string) => void;
  onModelLoading: () => void;
  onRecording: () => void;
  onError: (code: VoiceErrorCode, message: string) => void;
}

let transcriber: MicrophoneTranscriber | null = null;
let latestText = "";
let isRecording = false;

function mapMoonshineError(error: string): VoiceErrorCode {
  if (error === MoonshineError.PermissionDenied) {
    return "mic_denied";
  }

  return "transcription_failed";
}

export function isMoonshineRecording(): boolean {
  return isRecording;
}

export async function startMoonshinePtt(
  callbacks: MoonshinePttCallbacks,
): Promise<void> {
  if (isRecording) {
    return;
  }

  latestText = "";
  isRecording = true;

  const moonshineCallbacks: Partial<TranscriberCallbacks> = {
    onPermissionsRequested: () => {
      callbacks.onRecording();
    },
    onModelLoadStarted: () => {
      callbacks.onModelLoading();
    },
    onError: (error: string) => {
      isRecording = false;
      callbacks.onError(mapMoonshineError(error), error);
    },
    onTranscriptionUpdated: (text: string) => {
      latestText = text;
      callbacks.onPartial(text);
    },
    onTranscriptionCommitted: (text: string) => {
      latestText = text;
      callbacks.onPartial(text);
    },
  };

  transcriber = new MicrophoneTranscriber(
    MOONSHINE_MODEL_PATH,
    moonshineCallbacks,
    false,
  );

  await transcriber.start();
  callbacks.onRecording();
}

export async function stopMoonshinePtt(): Promise<string> {
  if (!transcriber) {
    isRecording = false;
    return latestText.trim();
  }

  transcriber.stop();
  transcriber = null;
  isRecording = false;

  return latestText.trim();
}
