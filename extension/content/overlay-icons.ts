export const ICON_CLOSE = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;

export const ICON_MIC = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" stroke="currentColor" stroke-width="1.6"/><path d="M6 11a6 6 0 0 0 12 0M12 17v3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;

export const ICON_KEYBOARD = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M7 10h.01M11 10h.01M15 10h.01M7 14h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;

export const ICON_SEND = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"><path d="m5 12 14-6-6 14-2-5-6-3Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>`;

export const ICON_SPARK = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true"><path d="M12 2l1.4 4.6L18 8l-4.6 1.4L12 14l-1.4-4.6L6 8l4.6-1.4L12 2Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M18 15l.8 2.6L21.4 18l-2.6.8L18 21.4l-.8-2.6L14.6 18l2.6-.8L18 15Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>`;

export function setButtonIcon(button: HTMLButtonElement, svg: string): void {
  button.innerHTML = svg;
}
