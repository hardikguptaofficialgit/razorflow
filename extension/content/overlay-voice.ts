import type { OverlayElements } from "./overlay-dom";
import { bindPushToTalkButton } from "../shared/voice/ptt";
import type {
  VoiceConfigResponse,
  VoiceStatusMessage,
  VoiceTranscriptMessage,
} from "../shared/voice/types";
import { showToast } from "./overlay-controls";

export function initOverlayVoice(elements: OverlayElements): void {
  const voiceButton = elements.voiceButton;

  void chrome.runtime
    .sendMessage({ type: "GET_VOICE_CONFIG" })
    .then((response: VoiceConfigResponse | undefined) => {
      if (!response?.enabled) {
        elements.root.setAttribute("data-voice-enabled", "false");
        voiceButton.hidden = true;
        return;
      }

      elements.root.setAttribute("data-voice-enabled", "true");
      voiceButton.hidden = false;

      bindPushToTalkButton(voiceButton, "overlay", (text) => {
        showToast(elements, text);
      });
    });

  chrome.runtime.onMessage.addListener((message: unknown) => {
    if (!message || typeof message !== "object") {
      return;
    }

    const payload = message as { type?: string; source?: string };
    if (payload.source && payload.source !== "overlay") {
      return;
    }

    if (payload.type === "VOICE_STATUS") {
      const status = message as VoiceStatusMessage;
      if (status.text) {
        showToast(elements, status.text, { error: status.state === "error" });
      }

      if (status.state === "recording") {
        elements.root.setAttribute("data-state", "listening");
        elements.commandDock
          .querySelector(".rf-dock-status")
          ?.setAttribute("data-state", "listening");
        elements.statusLabel.textContent = "Listening";
      }
      return;
    }

    if (payload.type === "VOICE_TRANSCRIPT") {
      const transcript = message as VoiceTranscriptMessage;
      showToast(elements, transcript.text);
    }
  });
}
