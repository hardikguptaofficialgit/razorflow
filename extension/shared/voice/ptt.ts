import type { VoiceSource } from "./types";

export function sendVoicePttStart(source: VoiceSource): void {
  void chrome.runtime.sendMessage({ type: "VOICE_PTT_START", source });
}

export function sendVoicePttStop(source: VoiceSource): void {
  void chrome.runtime.sendMessage({ type: "VOICE_PTT_STOP", source });
}

export function bindPushToTalkButton(
  button: HTMLButtonElement,
  source: VoiceSource,
  onStatusText?: (text: string) => void,
): void {
  let holding = false;

  const start = (event: Event) => {
    event.preventDefault();
    if (holding) {
      return;
    }
    holding = true;
    button.setAttribute("data-pressed", "true");
    onStatusText?.("Hold and speak…");
    sendVoicePttStart(source);
  };

  const stop = (event: Event) => {
    event.preventDefault();
    if (!holding) {
      return;
    }
    holding = false;
    button.removeAttribute("data-pressed");
    onStatusText?.("Transcribing…");
    sendVoicePttStop(source);
  };

  button.addEventListener("pointerdown", start);
  button.addEventListener("pointerup", stop);
  button.addEventListener("pointerleave", stop);
  button.addEventListener("pointercancel", stop);
}
