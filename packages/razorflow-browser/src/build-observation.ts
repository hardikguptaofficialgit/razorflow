/**
 * Generic DOM → BrowserObservation builder (site-agnostic).
 * Environments call this from observe(); commerce hints are optional overlays.
 */

import type {
  BrowserObservation,
  ElementRole,
  InteractiveElement,
  PageContextWire,
  SemanticGroup,
} from "@strykerinside/razorflow-protocol";

const INTERACTIVE_SELECTOR =
  'a,button,input,textarea,select,[role="button"],[role="link"],[role="searchbox"],[contenteditable="true"]';

const MAX_ELEMENTS = 120;
const MAX_TEXT_SAMPLE = 2000;

function truncate(value: string, max = 120): string {
  const trimmed = value.trim().replace(/\s+/g, " ");
  if (trimmed.length <= max) {
    return trimmed;
  }
  return `${trimmed.slice(0, max - 1)}…`;
}

function inferRole(element: HTMLElement): ElementRole {
  if (element instanceof HTMLInputElement) {
    if (element.type === "search" || element.getAttribute("role") === "search") {
      return "search";
    }
    if (element.type === "checkbox") {
      return "checkbox";
    }
    if (element.type === "radio") {
      return "radio";
    }
    return "input";
  }
  if (element instanceof HTMLTextAreaElement) {
    return "textarea";
  }
  if (element instanceof HTMLSelectElement) {
    return "select";
  }
  if (
    element instanceof HTMLButtonElement ||
    element.getAttribute("role") === "button"
  ) {
    return "button";
  }
  if (element.getAttribute("role") === "tab") {
    return "tab";
  }
  if (element.closest("[role='dialog'],dialog")) {
    return "dialog";
  }
  return "link";
}

function isVisible(element: HTMLElement, exclude?: (el: Element) => boolean): boolean {
  if (exclude?.(element)) {
    return false;
  }
  const style = window.getComputedStyle(element);
  if (
    style.display === "none" ||
    style.visibility === "hidden" ||
    Number(style.opacity) === 0
  ) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return rect.width > 2 && rect.height > 2;
}

function collectRanked(
  root: Document | HTMLElement,
  exclude?: (el: Element) => boolean,
): HTMLElement[] {
  const nodes = root.querySelectorAll<HTMLElement>(INTERACTIVE_SELECTOR);
  const ranked: HTMLElement[] = [];
  for (const node of nodes) {
    if (ranked.length >= MAX_ELEMENTS) {
      break;
    }
    if (isVisible(node, exclude)) {
      ranked.push(node);
    }
  }
  return ranked;
}

function toInteractiveElement(
  element: HTMLElement,
  index: number,
  groupId?: string,
): InteractiveElement {
  const rect = element.getBoundingClientRect();
  const href =
    element instanceof HTMLAnchorElement
      ? element.href
      : element.getAttribute("href") ?? "";
  const value =
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement
      ? element.value
      : "";
  const enabled = !(
    element.hasAttribute("disabled") ||
    element.getAttribute("aria-disabled") === "true"
  );
  return {
    id: `e${index}`,
    index,
    role: inferRole(element),
    tag: element.tagName.toLowerCase(),
    text: truncate(element.textContent ?? ""),
    ariaLabel: truncate(element.getAttribute("aria-label") ?? ""),
    placeholder: truncate(element.getAttribute("placeholder") ?? ""),
    href: href ? truncate(href, 200) : "",
    value: value ? truncate(value, 80) : "",
    visible: true,
    enabled,
    clickable:
      enabled &&
      (element instanceof HTMLAnchorElement ||
        element instanceof HTMLButtonElement ||
        element.getAttribute("role") === "button" ||
        element.getAttribute("role") === "link"),
    typeable:
      enabled &&
      (element instanceof HTMLInputElement ||
        element instanceof HTMLTextAreaElement ||
        element instanceof HTMLSelectElement),
    bbox: {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    },
    groupId,
  };
}

function buildSemanticGroups(
  ranked: HTMLElement[],
  elements: InteractiveElement[],
): SemanticGroup[] {
  const groups: SemanticGroup[] = [];
  let groupCounter = 0;

  const addGroup = (
    kind: SemanticGroup["kind"],
    label: string,
    container: Element,
    childSelector: string,
  ): void => {
    const children = container.querySelectorAll<HTMLElement>(childSelector);
    const ids: string[] = [];
    for (const child of children) {
      const idx = ranked.indexOf(child);
      if (idx >= 0) {
        const id = `e${idx + 1}`;
        ids.push(id);
        const el = elements.find((e) => e.id === id);
        if (el) {
          el.groupId = `g${groupCounter}`;
        }
      }
    }
    if (ids.length > 0) {
      groups.push({
        id: `g${groupCounter}`,
        kind,
        label: truncate(label, 80),
        elementIds: ids,
      });
      groupCounter += 1;
    }
  };

  for (const form of document.querySelectorAll("form")) {
    addGroup(
      "form",
      form.getAttribute("aria-label") ?? form.getAttribute("name") ?? "Form",
      form,
      "input,textarea,select,button,[role='button']",
    );
  }

  for (const nav of document.querySelectorAll("nav,[role='navigation']")) {
    addGroup("navigation", "Navigation", nav, "a,[role='link']");
  }

  for (const dialog of document.querySelectorAll("[role='dialog'],dialog")) {
    addGroup("dialog", "Dialog", dialog, "button,a,[role='button']");
  }

  for (const card of document.querySelectorAll(
    "article,.card,[class*='card'],li.product,div.product",
  )) {
    const title =
      card.querySelector("h1,h2,h3,h4,[class*='title']")?.textContent ?? "Card";
    addGroup("card", title, card, "a,button,h1,h2,h3,h4");
  }

  return groups;
}

function pageSignals(): string[] {
  const signals: string[] = [];
  const bodyText = (document.body?.innerText ?? "").toLowerCase();
  if (document.querySelector("form")) {
    signals.push("has_form");
  }
  if (document.querySelector("nav,[role='navigation']")) {
    signals.push("has_navigation");
  }
  if (document.querySelector("[role='dialog'],dialog")) {
    signals.push("has_dialog");
  }
  if (bodyText.includes("sign in") || bodyText.includes("log in")) {
    signals.push("may_require_login");
  }
  if (document.querySelector("input[type='search'],[role='searchbox']")) {
    signals.push("has_search");
  }
  return signals;
}

export interface BuildObservationOptions {
  root?: Document | HTMLElement;
  exclude?: (el: Element) => boolean;
  screenshotDataUrl?: string;
  hints?: BrowserObservation["hints"];
}

/** Build a generic BrowserObservation from the live DOM. */
export function buildBrowserObservation(
  options: BuildObservationOptions = {},
): BrowserObservation {
  const root = options.root ?? document;
  const ranked = collectRanked(root, options.exclude);
  const elements = ranked.map((el, i) => toInteractiveElement(el, i + 1));
  const groups = buildSemanticGroups(ranked, elements);

  for (const group of groups) {
    for (const id of group.elementIds) {
      const el = elements.find((e) => e.id === id);
      if (el) {
        el.groupId = group.id;
      }
    }
  }

  const visibleText = truncate(document.body?.innerText ?? "", MAX_TEXT_SAMPLE);

  return {
    url: window.location.href,
    title: document.title,
    path: window.location.pathname + window.location.search,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    elements,
    groups,
    visibleTextSample: visibleText,
    signals: pageSignals(),
    hints: options.hints,
    screenshotDataUrl: options.screenshotDataUrl,
    capturedAt: Date.now(),
  };
}

/** Convert BrowserObservation to wire-compatible PageContextWire. */
export function observationToWire(obs: BrowserObservation): PageContextWire {
  return {
    title: obs.title,
    url: obs.url,
    elements: obs.elements.map((el) => ({
      index: el.index,
      role: el.role === "textarea" || el.role === "select" ? "input" : el.role,
      tag: el.tag,
      text: el.text,
      placeholder: el.placeholder,
      ariaLabel: el.ariaLabel,
      href: el.href || undefined,
      value: el.value || undefined,
      enabled: el.enabled,
      bboxX: el.bbox?.x,
      bboxY: el.bbox?.y,
      bboxWidth: el.bbox?.width,
      bboxHeight: el.bbox?.height,
    })),
    products: obs.hints?.listings?.map((l) => ({
      title: l.title,
      priceText: l.subtitle,
      ratingText: "",
      reviewCountText: "",
      availabilityText: "",
      elementIndex: l.linkElementId
        ? Number.parseInt(l.linkElementId.replace(/^e/, ""), 10)
        : undefined,
      addToCartElementIndex: l.actionElementId
        ? Number.parseInt(l.actionElementId.replace(/^e/, ""), 10)
        : undefined,
    })),
    cartLines: obs.hints?.cart?.lines.map((line) => ({
      title: line.title,
      quantity: line.quantity,
      removeElementIndex: line.removeElementId
        ? Number.parseInt(line.removeElementId.replace(/^e/, ""), 10)
        : undefined,
    })),
    screenshotDataUrl: obs.screenshotDataUrl,
  };
}
