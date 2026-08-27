import type { OverlayElements } from "./overlay-dom";

const CURSOR_TRANSITION_MS = 180;
const HIGHLIGHT_VISIBLE_MS = 1200;

export function animateCursorTo(
  elements: OverlayElements,
  x: number,
  y: number,
): void {
  elements.cursor.classList.add("rf-cursor--moving");
  elements.cursor.style.transform = `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0)`;

  window.setTimeout(() => {
    elements.cursor.classList.remove("rf-cursor--moving");
  }, CURSOR_TRANSITION_MS);
}

export function flashHighlight(elements: OverlayElements): void {
  elements.highlight.classList.remove("rf-highlight--active");
  void elements.highlight.offsetWidth;
  elements.highlight.classList.add("rf-highlight--active");

  window.setTimeout(() => {
    elements.highlight.classList.remove("rf-highlight--active");
  }, HIGHLIGHT_VISIBLE_MS);
}

export function pulseStatus(elements: OverlayElements): void {
  const status = elements.commandDock.querySelector(".rf-dock-status");
  if (!status) {
    return;
  }

  status.classList.remove("rf-dock-status--pulse");
  void status.getBoundingClientRect();
  status.classList.add("rf-dock-status--pulse");
}
