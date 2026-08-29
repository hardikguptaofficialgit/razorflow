import {
  suggestionsForPhase,
  type TaskSuggestion,
} from "../shared/task-suggestions";
import type { OverlayElements, OverlayRunPhase } from "./overlay-dom";

let startTaskFromSuggestion: ((task: string) => void) | null = null;

export function registerSuggestionTaskStarter(
  starter: (task: string) => void,
): void {
  startTaskFromSuggestion = starter;
}

export function refreshTaskSuggestions(
  elements: OverlayElements,
  runPhase: OverlayRunPhase,
): void {
  const container = elements.suggestionsContainer;
  if (!container) {
    return;
  }

  const expanded = elements.commandDock.dataset.inputExpanded === "true";
  const hasActiveRun = runPhase === "running" || runPhase === "planning";
  const suggestions = suggestionsForPhase(runPhase, hasActiveRun);

  container.replaceChildren();
  if (!expanded || suggestions.length === 0) {
    container.hidden = true;
    return;
  }

  container.hidden = false;
  for (const suggestion of suggestions) {
    container.appendChild(createSuggestionChip(suggestion));
  }
}

function createSuggestionChip(suggestion: TaskSuggestion): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "rf-dock-suggestion";
  button.textContent = suggestion.label;
  button.title = suggestion.task;
  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    startTaskFromSuggestion?.(suggestion.task);
  });
  return button;
}
