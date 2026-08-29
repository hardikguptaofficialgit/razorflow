"use client";

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return Boolean(target.closest('[contenteditable="true"]'));
}

function isModalOpen(): boolean {
  return Boolean(
    document.querySelector('[role="dialog"][aria-modal="true"]'),
  );
}

export function shouldIgnoreVoiceHotkey(event: KeyboardEvent): boolean {
  if (event.code !== "Space" && event.key !== " ") {
    return true;
  }
  if (event.repeat) {
    return true;
  }
  if (event.ctrlKey || event.altKey || event.metaKey) {
    return true;
  }
  if (isEditableTarget(event.target)) {
    return true;
  }
  if (isModalOpen()) {
    return true;
  }
  return false;
}

export function isSpaceVoiceKey(event: KeyboardEvent): boolean {
  return event.code === "Space" || event.key === " ";
}
