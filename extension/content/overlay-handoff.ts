import type { OverlayElements } from "./overlay-dom";

type HandoffAction = "resume" | "cancel";

export function bindWaitingPanelActions(
  elements: OverlayElements,
  onAction: (action: HandoffAction) => void,
): void {
  elements.waitingPanel
    .querySelector<HTMLButtonElement>('[data-action="resume"]')
    ?.addEventListener("click", () => onAction("resume"));

  elements.waitingPanel
    .querySelector<HTMLButtonElement>('[data-action="cancel"]')
    ?.addEventListener("click", () => onAction("cancel"));
}

export function sendOverlayHandoffAction(action: HandoffAction): void {
  void chrome.runtime.sendMessage({
    type: action === "resume" ? "OVERLAY_RESUME_RUN" : "OVERLAY_CANCEL_RUN",
  });
}
