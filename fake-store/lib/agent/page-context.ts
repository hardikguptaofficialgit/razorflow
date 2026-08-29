import type {
  PageCartLineSummary,
  PageContext,
  PageElementSummary,
  PageProductSummary,
  TargetRole,
} from "@/lib/agent/bridge-protocol";
import {
  collectRankedInteractiveElements,
  findRankedIndex,
  isVisible,
  MAX_RANKED_ELEMENTS,
} from "@/lib/agent/dom-targeting";

/** Must stay aligned with agent-backend/core/protocol.py PageContext limits. */
export const MAX_PAGE_CONTEXT_PRODUCTS = 32;

function truncate(value: string, max = 120): string {
  const trimmed = value.trim().replace(/\s+/g, " ");
  if (trimmed.length <= max) {
    return trimmed;
  }
  return `${trimmed.slice(0, max - 1)}…`;
}

function inferRole(element: HTMLElement): TargetRole {
  if (element instanceof HTMLInputElement) {
    if (element.type === "search" || element.getAttribute("role") === "search") {
      return "search";
    }
    return "input";
  }
  if (element instanceof HTMLTextAreaElement) {
    return "input";
  }
  if (
    element instanceof HTMLButtonElement ||
    element.getAttribute("role") === "button"
  ) {
    return "button";
  }
  return "link";
}

function toElementSummary(
  index: number,
  element: HTMLElement,
): PageElementSummary {
  const rect = element.getBoundingClientRect();
  const href =
    element instanceof HTMLAnchorElement
      ? element.href
      : element.getAttribute("href") ?? "";
  const value =
    element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement
      ? element.value
      : "";
  return {
    index,
    role: inferRole(element),
    tag: element.tagName.toLowerCase(),
    text: truncate(element.textContent ?? ""),
    placeholder: truncate(element.getAttribute("placeholder") ?? ""),
    ariaLabel: truncate(element.getAttribute("aria-label") ?? ""),
    href: href ? truncate(href, 200) : undefined,
    value: value ? truncate(value, 80) : undefined,
    enabled: !(
      element.hasAttribute("disabled") ||
      element.getAttribute("aria-disabled") === "true"
    ),
    bboxX: Math.round(rect.x),
    bboxY: Math.round(rect.y),
    bboxWidth: Math.round(rect.width),
    bboxHeight: Math.round(rect.height),
  };
}

function collectProducts(ranked: HTMLElement[]): PageProductSummary[] {
  const cards = document.querySelectorAll<HTMLElement>(
    "[data-rf-product-card], article.rf-card",
  );
  const products: PageProductSummary[] = [];

  for (const card of cards) {
    if (!isVisible(card)) {
      continue;
    }

    const titleEl =
      card.querySelector<HTMLElement>("[data-rf-product-title]") ??
      card.querySelector<HTMLElement>("h1,h2,h3");
    const priceEl = card.querySelector<HTMLElement>("[data-rf-product-price]");
    const ratingEl = card.querySelector<HTMLElement>("[data-rf-product-rating]");
    const stockEl = card.querySelector<HTMLElement>("[data-rf-product-stock]");
    const linkEl = card.querySelector<HTMLElement>("a[href]");
    const addBtn = card.querySelector<HTMLElement>("[data-rf-add-to-cart]");

    const title = truncate(titleEl?.textContent ?? "");
    if (!title) {
      continue;
    }

    products.push({
      title,
      priceText: truncate(priceEl?.textContent ?? ""),
      ratingText: truncate(ratingEl?.textContent ?? ""),
      reviewCountText: "",
      availabilityText: truncate(stockEl?.textContent ?? ""),
      elementIndex: findRankedIndex(ranked, linkEl),
      addToCartElementIndex: findRankedIndex(ranked, addBtn),
    });

    if (products.length >= MAX_PAGE_CONTEXT_PRODUCTS) {
      break;
    }
  }

  return products;
}

function collectCartLines(ranked: HTMLElement[]): PageCartLineSummary[] {
  const lines = document.querySelectorAll<HTMLElement>("[data-rf-cart-line]");
  const cartLines: PageCartLineSummary[] = [];

  for (const line of lines) {
    if (!isVisible(line)) {
      continue;
    }
    const titleEl =
      line.querySelector<HTMLElement>("[data-rf-product-title]") ??
      line.querySelector<HTMLElement>("h3");
    const title = truncate(titleEl?.textContent ?? "");
    if (!title) {
      continue;
    }
    const qtyText =
      line.querySelector<HTMLElement>("[data-rf-line-qty]")?.textContent ??
      line.querySelector("span")?.textContent ??
      "1";
    const quantity = Number.parseInt(qtyText.trim(), 10) || 1;
    const removeBtn = line.querySelector<HTMLElement>("[data-rf-remove-item]");
    cartLines.push({
      title,
      quantity,
      removeElementIndex: findRankedIndex(ranked, removeBtn),
    });
  }

  return cartLines;
}

function readHeaderCartCount(): number {
  const raw =
    document.querySelector("[data-rf-cart-count]")?.textContent?.trim() ?? "0";
  const parsed = Number.parseInt(raw.replace(/\D/g, ""), 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Snapshot the live tab for the agent planner. */
export function extractPageContext(): PageContext {
  const ranked = collectRankedInteractiveElements();
  const elements = ranked.map((element, position) =>
    toElementSummary(position + 1, element),
  );

  const orderTotal = document.querySelector<HTMLElement>("[data-rf-order-total]");
  if (orderTotal && isVisible(orderTotal)) {
    elements.unshift({
      index: 0,
      role: "button",
      tag: "data-rf-order-total",
      text: truncate(orderTotal.textContent ?? ""),
      placeholder: "",
      ariaLabel: "order total",
    });
  }

  const authModal = document.querySelector<HTMLElement>(
    "[data-rf-auth-modal][data-rf-auth-next*='checkout']",
  );
  if (authModal && isVisible(authModal)) {
    elements.unshift({
      index: 0,
      role: "button",
      tag: "data-rf-checkout-auth-gate",
      text: "Sign in to checkout",
      placeholder: "",
      ariaLabel: "checkout-login-gate",
    });
  }

  const authGate = document.querySelector<HTMLElement>("[data-rf-auth-required]");
  if (authGate && isVisible(authGate)) {
    elements.unshift({
      index: 0,
      role: "button",
      tag: "data-rf-auth-required",
      text: truncate(authGate.textContent ?? "Sign in required"),
      placeholder: "",
      ariaLabel: "Sign in to checkout",
    });
  }

  const checkoutGate = document.querySelector<HTMLElement>("[data-rf-checkout-gate]");
  if (checkoutGate && isVisible(checkoutGate) && !authGate) {
    elements.unshift({
      index: 0,
      role: "button",
      tag: "data-rf-checkout-gate",
      text: truncate(checkoutGate.textContent ?? "Sign in to checkout"),
      placeholder: "",
      ariaLabel: "Sign in to checkout",
    });
  }

  const headerCartCount = readHeaderCartCount();
  if (headerCartCount > 0) {
    elements.unshift({
      index: 0,
      role: "link",
      tag: "data-rf-cart-badge",
      text: `Cart (${headerCartCount})`,
      placeholder: "",
      ariaLabel: `Cart, ${headerCartCount} items`,
    });
  }

  return {
    title: document.title,
    url: window.location.href,
    elements: elements.slice(0, MAX_RANKED_ELEMENTS),
    products: collectProducts(ranked),
    cartLines: collectCartLines(ranked),
  };
}
