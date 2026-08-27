import type { OverlayElements } from "./overlay-dom";
import {
  ICON_CLOSE,
  ICON_KEYBOARD,
  ICON_MIC,
  ICON_SEND,
  setButtonIcon,
} from "./overlay-icons";

function applyInputContrast(input: HTMLInputElement): void {
  input.style.setProperty("color", "#f5f5f7", "important");
  input.style.setProperty("-webkit-text-fill-color", "#f5f5f7", "important");
  input.style.setProperty("caret-color", "#ffffff", "important");
  input.style.setProperty("background-color", "#1a1a1e", "important");
}

function expandInput(elements: OverlayElements): void {
  elements.commandDock.dataset.inputExpanded = "true";
  elements.textToggleButton.setAttribute("aria-expanded", "true");
  elements.textToggleButton.dataset.active = "true";
  applyInputContrast(elements.textInput);
  window.requestAnimationFrame(() => {
    elements.textInput.focus({ preventScroll: true });
    applyInputContrast(elements.textInput);
  });
}

function collapseInput(elements: OverlayElements): void {
  elements.commandDock.dataset.inputExpanded = "false";
  elements.textToggleButton.setAttribute("aria-expanded", "false");
  elements.textToggleButton.dataset.active = "false";
  elements.textInput.blur();
}

export function bindOverlayControls(elements: OverlayElements): void {
  const {
    textToggleButton,
    textInput,
    sendTaskButton,
    collapseTextButton,
    voiceButton,
  } = elements;

  if (!textToggleButton || !textInput || !sendTaskButton) {
    return;
  }

  setButtonIcon(textToggleButton, ICON_KEYBOARD);
  setButtonIcon(sendTaskButton, ICON_SEND);
  if (collapseTextButton) {
    setButtonIcon(collapseTextButton, ICON_CLOSE);
  }
  setButtonIcon(voiceButton, ICON_MIC);
  applyInputContrast(textInput);

  textToggleButton.setAttribute("aria-expanded", "false");
  textToggleButton.dataset.active = "false";

  textToggleButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const expanded = elements.commandDock.dataset.inputExpanded === "true";
    if (expanded) {
      collapseInput(elements);
    } else {
      expandInput(elements);
    }
  });

  collapseTextButton?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    collapseInput(elements);
  });

  const submitTask = (): void => {
    const task = textInput.value.trim();
    if (!task) {
      expandInput(elements);
      return;
    }

    const runId = crypto.randomUUID();
    void chrome.runtime.sendMessage({
      type: "OVERLAY_START_TASK",
      task,
      runId,
    });
    textInput.value = "";
    collapseInput(elements);
    showToast(elements, "Starting task...");
  };

  sendTaskButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    submitTask();
  });

  textInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitTask();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      collapseInput(elements);
    }
  });

  textInput.addEventListener("focus", () => {
    applyInputContrast(textInput);
  });

  textInput.addEventListener("input", () => {
    applyInputContrast(textInput);
  });
}

export function showToast(
  elements: OverlayElements,
  message: string,
  options: { error?: boolean } = {},
): void {
  elements.toast.hidden = false;
  elements.toast.textContent = message;
  if (options.error) {
    elements.toast.dataset.error = "true";
  } else {
    elements.toast.removeAttribute("data-error");
  }
}

export function hideToast(elements: OverlayElements): void {
  elements.toast.hidden = true;
  elements.toast.textContent = "";
  elements.toast.removeAttribute("data-error");
}
