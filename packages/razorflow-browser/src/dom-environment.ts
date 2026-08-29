/**
 * Reference BrowserEnvironment — executes wire ActionSteps against the live DOM.
 * Site-agnostic; commerce-specific hooks (cart badges) are optional.
 */

import type { ActionStep } from "@hardik21232323/razorflow-protocol";
import type { BrowserEnvironment, StepResult } from "./environment.js";
import {
  buildBrowserObservation,
  observationToWire,
} from "./build-observation.js";

const INTERACTIVE_SELECTOR =
  'a,button,input,textarea,select,[role="button"],[role="link"],[role="searchbox"],[contenteditable="true"]';

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isVisible(el: Element): boolean {
  if (!(el instanceof HTMLElement)) {
    return false;
  }
  const style = window.getComputedStyle(el);
  if (
    style.display === "none" ||
    style.visibility === "hidden" ||
    Number(style.opacity) === 0
  ) {
    return false;
  }
  const rect = el.getBoundingClientRect();
  return rect.width > 2 && rect.height > 2;
}

function rankedElements(): HTMLElement[] {
  return Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR)).filter(
    isVisible,
  ) as HTMLElement[];
}

function findTarget(step: ActionStep): HTMLElement | null {
  if (step.action !== "click_element" && step.action !== "type_in_element") {
    return null;
  }
  const ranked = rankedElements();
  if ("elementIndex" in step && step.elementIndex) {
    const el = ranked[step.elementIndex - 1];
    if (el) {
      return el;
    }
  }
  const needle = ("matchText" in step ? step.matchText : "")?.toLowerCase() ?? "";
  if (needle) {
    for (const el of ranked) {
      const blob = `${el.textContent ?? ""} ${el.getAttribute("aria-label") ?? ""} ${el.getAttribute("placeholder") ?? ""} ${el.getAttribute("value") ?? ""}`.toLowerCase();
      if (blob.includes(needle)) {
        return el;
      }
    }
  }
  if (step.action === "type_in_element" && step.role === "search") {
    return document.querySelector<HTMLElement>(
      'input[type="search"], input[name="search"], input[name="q"], [role="searchbox"]',
    );
  }
  return null;
}

async function executeScroll(step: Extract<ActionStep, { action: "scroll_page" }>): Promise<StepResult> {
  const before = window.scrollY;
  const dir = step.direction ?? "down";
  const amount = step.amountPx ?? 600;
  if (dir === "top") {
    window.scrollTo(0, 0);
  } else if (dir === "bottom") {
    window.scrollTo(0, document.documentElement.scrollHeight);
  } else if (dir === "up") {
    window.scrollBy(0, -amount);
  } else {
    window.scrollBy(0, amount);
  }
  await sleep(300);
  return { success: true, verified: window.scrollY !== before };
}

async function executeType(step: Extract<ActionStep, { action: "type_in_element" }>): Promise<StepResult> {
  let el = findTarget(step);
  if (!el && step.matchText) {
    const needle = step.matchText.toLowerCase();
    for (const input of document.querySelectorAll("input,textarea")) {
      const blob = `${input.getAttribute("name") ?? ""} ${input.id} ${input.getAttribute("placeholder") ?? ""}`.toLowerCase();
      if (blob.includes(needle)) {
        el = input as HTMLElement;
        break;
      }
    }
  }
  if (
    !el ||
    !(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)
  ) {
    return { success: false, error: "No typeable target" };
  }
  const before = location.href;
  const text = step.text ?? "";
  el.focus();
  const nativeSetter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  if (nativeSetter && el instanceof HTMLInputElement) {
    nativeSetter.call(el, text);
  } else {
    el.value = text;
  }
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  if (el.form) {
    el.form.requestSubmit?.();
  } else {
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  }
  await sleep(800);
  const changed =
    location.href !== before ||
    document.body.innerText.toLowerCase().includes(text.toLowerCase().slice(0, 8));
  return { success: text.length > 0, verified: changed };
}

async function executeClick(step: Extract<ActionStep, { action: "click_element" }>): Promise<StepResult> {
  const beforeUrl = location.href;
  const el = findTarget(step);
  if (!el) {
    return { success: false, error: "Click target not found" };
  }
  el.scrollIntoView({ block: "center" });
  await sleep(120);
  el.click();
  await sleep(500);
  return {
    success: true,
    verified: location.href !== beforeUrl || Boolean(step.matchText),
  };
}

export class DomBrowserEnvironment implements BrowserEnvironment {
  async observe() {
    return buildBrowserObservation();
  }

  async observeWire() {
    return observationToWire(await this.observe());
  }

  async executeStep(
    step: ActionStep,
    onProgress?: (summary: string) => void,
  ): Promise<StepResult> {
    onProgress?.(step.action);
    switch (step.action) {
      case "scroll_page":
        return executeScroll(step);
      case "wait":
        await sleep(Math.min(5000, step.durationMs ?? 500));
        return { success: true, verified: true };
      case "go_back": {
        const before = location.href;
        history.back();
        await sleep(500);
        return {
          success: location.href !== before,
          verified: location.href !== before,
        };
      }
      case "navigate_url": {
        const before = location.href;
        location.assign(step.url);
        await sleep(600);
        return {
          success: location.href !== before,
          verified: location.href.includes(step.url) || location.href !== before,
        };
      }
      case "type_in_element":
        return executeType(step);
      case "click_element":
        return executeClick(step);
      case "highlight_element": {
        const el = findTarget(step);
        if (el) {
          el.scrollIntoView({ block: "center" });
        }
        return { success: Boolean(el), verified: Boolean(el) };
      }
      case "wait_for_user":
      case "ready_for_payment_link":
      case "set_state":
        return { success: true, verified: true };
      default:
        return { success: false, error: `Unsupported action: ${(step as ActionStep).action}` };
    }
  }

  async waitForStable() {
    await sleep(400);
    return this.observeWire();
  }
}
