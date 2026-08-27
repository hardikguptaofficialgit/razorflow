import type { DomTargetMatch, TargetRole } from "../shared/types";
import {
  findByRole,
  findButtonElement,
  isElementActionable,
  refreshTargetMatch,
  sleep,
} from "./dom-targeting";
import { setNativeInputValue, submitSearchInput } from "./dom-input";
import type { OverlayController } from "./overlay-state";

const PAUSE_SHORT_MS = 90;
const PAUSE_MEDIUM_MS = 160;
const CURSOR_ANIMATION_MS = 180;
const TYPE_CHAR_MIN_MS = 8;
const TYPE_CHAR_MAX_MS = 16;
const TYPE_FAST_THRESHOLD = 18;
const SCROLL_SETTLE_MS = 140;
const PAGE_CHANGE_POLL_MS = 70;
const PAGE_CHANGE_TIMEOUT_MS = 1400;

export type ActionOutcome = {
  ok: boolean;
  error?: string;
  verified?: boolean;
};

function pageSignature(): string {
  const products = document.querySelectorAll(
    "[data-asin], [data-component-type='s-search-result'], [class*='product'], [data-product]",
  ).length;
  const cartHint =
    document.body?.innerText?.match(/cart\s*\(?\d+\)?/i)?.[0] ?? "";
  return `${location.href}|${document.title}|${products}|${cartHint.slice(0, 24)}`;
}

async function waitForPageChange(
  before: string,
  timeoutMs = PAGE_CHANGE_TIMEOUT_MS,
): Promise<boolean> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (pageSignature() !== before) {
      return true;
    }
    await sleep(PAGE_CHANGE_POLL_MS);
  }
  return pageSignature() !== before;
}

function isTypeableElement(
  element: HTMLElement,
): element is HTMLInputElement | HTMLTextAreaElement {
  return (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement
  );
}

function clickPoint(element: HTMLElement): { x: number; y: number } {
  const rect = element.getBoundingClientRect();
  const width = Math.max(rect.width, 1);
  const height = Math.max(rect.height, 1);
  // Prefer a safe interior point (not the extreme edge).
  return {
    x: rect.left + Math.min(Math.max(width * 0.5, 4), width - 4),
    y: rect.top + Math.min(Math.max(height * 0.5, 4), height - 4),
  };
}

function dispatchPointerSequence(
  element: HTMLElement,
  point: { x: number; y: number },
): void {
  const { x, y } = point;
  const common: MouseEventInit = {
    bubbles: true,
    cancelable: true,
    view: window,
    clientX: x,
    clientY: y,
    screenX: Math.round(x + window.screenX),
    screenY: Math.round(y + window.screenY),
    button: 0,
    buttons: 1,
  };

  if (typeof PointerEvent === "function") {
    element.dispatchEvent(
      new PointerEvent("pointerdown", {
        ...common,
        pointerId: 1,
        pointerType: "mouse",
        isPrimary: true,
      }),
    );
  }
  element.dispatchEvent(new MouseEvent("mousedown", common));

  if (typeof PointerEvent === "function") {
    element.dispatchEvent(
      new PointerEvent("pointerup", {
        ...common,
        buttons: 0,
        pointerId: 1,
        pointerType: "mouse",
        isPrimary: true,
      }),
    );
  }
  element.dispatchEvent(new MouseEvent("mouseup", { ...common, buttons: 0 }));
}

function performClick(element: HTMLElement, point: { x: number; y: number }): void {
  try {
    element.focus({ preventScroll: true });
  } catch {
    // Continue — not all elements accept focus.
  }
  dispatchPointerSequence(element, point);
  try {
    element.click();
  } catch {
    // Pointer/mouse events already fired.
  }
}

async function typeHumanLike(
  element: HTMLInputElement | HTMLTextAreaElement,
  text: string,
): Promise<void> {
  element.focus({ preventScroll: true });
  setNativeInputValue(element, "");

  if (text.length > TYPE_FAST_THRESHOLD) {
    setNativeInputValue(element, text);
    await sleep(PAUSE_SHORT_MS);
    return;
  }

  for (const character of text) {
    setNativeInputValue(element, element.value + character);
    const delay =
      TYPE_CHAR_MIN_MS +
      Math.floor(Math.random() * (TYPE_CHAR_MAX_MS - TYPE_CHAR_MIN_MS));
    await sleep(delay);
  }
}

function valueMatches(
  element: HTMLInputElement | HTMLTextAreaElement,
  text: string,
): boolean {
  return element.value.trim().toLowerCase() === text.trim().toLowerCase();
}

function resolveTarget(
  role: TargetRole,
  elementIndex?: number,
  matchText?: string,
): DomTargetMatch | null {
  const match = findByRole(role, elementIndex, matchText);
  if (!match) {
    return null;
  }
  if (!isElementActionable(match.element)) {
    return null;
  }
  return match;
}

export class ActionPlayer {
  private actionQueue: Promise<void> = Promise.resolve();

  constructor(private readonly controller: OverlayController) {}

  private enqueue<T>(task: () => Promise<T>): Promise<T> {
    const next = this.actionQueue.then(task);
    this.actionQueue = next.then(
      () => undefined,
      () => undefined,
    );
    return next;
  }

  async highlightElement(
    role: TargetRole,
    elementIndex?: number,
    matchText?: string,
  ): Promise<ActionOutcome> {
    return this.enqueue(async () => {
      const match = resolveTarget(role, elementIndex, matchText);
      if (!match) {
        return {
          ok: false,
          error: `Could not find a usable ${role} target on this page.`,
        };
      }

      await this.animateToTarget(match);
      this.controller.showHighlight(match.rect);
      await sleep(PAUSE_SHORT_MS);
      return { ok: true, verified: true };
    });
  }

  async clickElement(
    role: TargetRole,
    elementIndex?: number,
    matchText?: string,
  ): Promise<ActionOutcome> {
    return this.enqueue(async () => {
      const match = resolveTarget(role, elementIndex, matchText);
      if (!match) {
        return {
          ok: false,
          error: `Failed: no clickable ${role} element found.`,
        };
      }

      this.controller.setState("acting");
      const before = pageSignature();
      await this.animateToTarget(match);

      const live = refreshTargetMatch(match);
      if (!isElementActionable(live.element)) {
        return {
          ok: false,
          error: "Failed: target became hidden or disabled before click.",
        };
      }

      const point = clickPoint(live.element);
      this.controller.showHighlight(live.rect);
      this.controller.moveCursor(point.x, point.y);
      await sleep(50);

      performClick(live.element, point);
      const changed = await waitForPageChange(before);

      // Soft verification: navigation/DOM signature change, or clickable control still live
      // (filters/toggles may not change URL).
      if (!changed && !document.contains(live.element)) {
        return {
          ok: false,
          error: "Failed: click removed the target without a usable page update.",
          verified: false,
        };
      }

      return { ok: true, verified: changed };
    });
  }

  async typeInElement(
    role: TargetRole,
    text: string,
    elementIndex?: number,
    matchText?: string,
  ): Promise<ActionOutcome> {
    return this.enqueue(async () => {
      if (!text.trim()) {
        return { ok: false, error: "Failed: empty text to type." };
      }

      const match = resolveTarget(role, elementIndex, matchText);
      if (!match || !isTypeableElement(match.element)) {
        return {
          ok: false,
          error: `Failed: no typeable ${role} field found.`,
        };
      }

      this.controller.setState("acting");
      await this.animateToTarget(match);

      const live = refreshTargetMatch(match);
      if (!isTypeableElement(live.element) || !isElementActionable(live.element)) {
        return {
          ok: false,
          error: "Failed: input became unavailable before typing.",
        };
      }

      const point = clickPoint(live.element);
      this.controller.showHighlight(live.rect);
      this.controller.moveCursor(point.x, point.y);

      performClick(live.element, point);
      await sleep(60);
      await typeHumanLike(live.element, text);

      if (!valueMatches(live.element, text)) {
        setNativeInputValue(live.element, text);
      }

      if (!valueMatches(live.element, text)) {
        return {
          ok: false,
          error: "Failed: typed value did not stick in the input.",
          verified: false,
        };
      }

      if (role === "search") {
        const before = pageSignature();
        submitSearchInput(live.element);
        const changed = await waitForPageChange(before);
        if (!changed) {
          // Search button fallback is planner/heuristic territory; report honest soft fail.
          await sleep(PAUSE_MEDIUM_MS);
          return {
            ok: true,
            verified: false,
            error: undefined,
          };
        }
        return { ok: true, verified: true };
      }

      await sleep(PAUSE_MEDIUM_MS);
      return { ok: true, verified: true };
    });
  }

  async runDemoFlow(text = "shampoo"): Promise<ActionOutcome> {
    const typed = await this.typeInElement("search", text);
    if (!typed.ok) {
      return typed;
    }
    const button = findButtonElement();
    if (!button) {
      return typed;
    }
    return this.clickElement("button", undefined, "search");
  }

  private async animateToTarget(match: DomTargetMatch): Promise<void> {
    match.element.scrollIntoView({
      behavior: "auto",
      block: "center",
      inline: "nearest",
    });
    await sleep(SCROLL_SETTLE_MS);

    const refreshed = refreshTargetMatch(match);
    match.rect = refreshed.rect;
    match.center = refreshed.center;

    const point = clickPoint(match.element);
    this.controller.showHighlight(match.rect);
    this.controller.moveCursor(point.x, point.y);
    await sleep(CURSOR_ANIMATION_MS);
  }
}
