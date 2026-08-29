/** Shared DOM ranking for page-context extraction and action execution. */

const AGENT_ROOT_SELECTOR = "[data-rf-agent-root]";
export const MAX_RANKED_ELEMENTS = 120;

export interface DomTargetMatch {
  element: HTMLElement;
  index: number;
}

export function isAgentUi(element: Element): boolean {
  return Boolean(element.closest(AGENT_ROOT_SELECTOR));
}

export function isVisible(element: HTMLElement): boolean {
  if (isAgentUi(element)) {
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

export function isElementActionable(element: HTMLElement): boolean {
  if (!isVisible(element)) {
    return false;
  }
  if (
    element.hasAttribute("disabled") ||
    element.getAttribute("aria-disabled") === "true"
  ) {
    return false;
  }
  return true;
}

function elementLabel(element: HTMLElement): string {
  return [
    element.getAttribute("data-rf-label"),
    element.getAttribute("aria-label"),
    element.getAttribute("placeholder"),
    element.textContent,
  ]
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function inferRole(element: HTMLElement): string {
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

function isCartNavigationNeedle(needle?: string): boolean {
  if (!needle) {
    return false;
  }
  const normalized = needle.toLowerCase();
  return normalized.includes("cart") && !normalized.includes("add to cart");
}

function isCheckoutNeedle(needle?: string): boolean {
  if (!needle) {
    return false;
  }
  const normalized = needle.toLowerCase();
  return normalized.includes("checkout") || normalized.includes("sign in");
}

function labelMatchesLoosely(needle: string, element: HTMLElement): boolean {
  const label = elementLabel(element);
  if (label.includes(needle)) {
    return true;
  }
  if (needle.includes("search") && (label.includes("search") || inferRole(element) === "search")) {
    return true;
  }
  if (isCartNavigationNeedle(needle) && (label.includes("cart") || element.matches("[data-rf-cart-link]"))) {
    return true;
  }
  if (isCheckoutNeedle(needle) && label.includes("checkout")) {
    return true;
  }
  const tokens = needle.split(/\s+/).filter((token) => token.length > 2);
  if (tokens.length === 0) {
    return true;
  }
  const matched = tokens.filter((token) => label.includes(token));
  return matched.length >= Math.ceil(tokens.length / 2);
}

export function findCartNavigationTarget(ranked: HTMLElement[]): DomTargetMatch | null {
  const cartLink = document.querySelector<HTMLElement>("[data-rf-cart-link]");
  if (cartLink && isElementActionable(cartLink)) {
    return {
      element: cartLink,
      index: findRankedIndex(ranked, cartLink) ?? 1,
    };
  }
  for (const candidate of ranked) {
    if (!(candidate instanceof HTMLAnchorElement)) {
      continue;
    }
    if (!candidate.href.includes("/cart")) {
      continue;
    }
    if (elementLabel(candidate).includes("cart")) {
      return {
        element: candidate,
        index: findRankedIndex(ranked, candidate) ?? 1,
      };
    }
  }
  return null;
}

export function findCheckoutTarget(ranked: HTMLElement[]): DomTargetMatch | null {
  const selectors = [
    "[data-rf-checkout-gate] button",
    "[data-rf-auth-required] button",
    "[data-rf-auth-modal][data-rf-auth-next*='checkout'] button[type='submit']",
    "[data-rf-go-checkout]",
    "a[href*='/checkout']",
  ];
  for (const selector of selectors) {
    const element = document.querySelector<HTMLElement>(selector);
    if (element && isElementActionable(element)) {
      return {
        element,
        index: findRankedIndex(ranked, element) ?? 1,
      };
    }
  }
  for (const candidate of ranked) {
    const label = elementLabel(candidate);
    if (!label.includes("checkout")) {
      continue;
    }
    if (label === "×" || label === "x") {
      continue;
    }
    return {
      element: candidate,
      index: findRankedIndex(ranked, candidate) ?? 1,
    };
  }
  return null;
}

export function isTypeableElement(
  element: HTMLElement,
): element is HTMLInputElement | HTMLTextAreaElement {
  if (element instanceof HTMLTextAreaElement) {
    return true;
  }
  if (element instanceof HTMLInputElement) {
    const type = (element.type || "text").toLowerCase();
    return !["button", "submit", "checkbox", "radio", "hidden", "file"].includes(
      type,
    );
  }
  return element.isContentEditable;
}

/** Stable ranked list used for elementIndex in planner + executor. */
export function collectRankedInteractiveElements(): HTMLElement[] {
  const selector = [
    "input:not([type=hidden])",
    "textarea",
    "button:not(:disabled)",
    "a[href]",
    "[role=button]",
    "[data-rf-interactive]",
  ].join(",");

  const nodes = document.querySelectorAll<HTMLElement>(selector);
  const ranked: HTMLElement[] = [];
  const seen = new Set<HTMLElement>();

  const push = (element: HTMLElement | null) => {
    if (!element || seen.has(element) || !isElementActionable(element)) {
      return;
    }
    seen.add(element);
    ranked.push(element);
  };

  for (const element of nodes) {
    if (!(element instanceof HTMLElement)) {
      continue;
    }
    if (element.closest("[data-rf-product-card], article.rf-card")) {
      continue;
    }
    push(element);
    if (ranked.length >= MAX_RANKED_ELEMENTS) {
      return ranked;
    }
  }

  const cards = document.querySelectorAll<HTMLElement>(
    "[data-rf-product-card], article.rf-card",
  );
  for (const card of cards) {
    if (!isVisible(card)) {
      continue;
    }
    push(card.querySelector<HTMLElement>("[data-rf-add-to-cart]"));
    push(card.querySelector<HTMLElement>("a[href]"));
    push(card.querySelector<HTMLElement>("button"));
    if (ranked.length >= MAX_RANKED_ELEMENTS) {
      return ranked;
    }
  }

  return ranked;
}

export function findRankedIndex(
  ranked: HTMLElement[],
  target: HTMLElement | null,
): number | undefined {
  if (!target) {
    return undefined;
  }
  const position = ranked.findIndex((entry) => entry === target);
  return position >= 0 ? position + 1 : undefined;
}

export function findByRole(
  role: string,
  elementIndex?: number,
  matchText?: string,
): DomTargetMatch | null {
  const ranked = collectRankedInteractiveElements();
  const needle = matchText?.toLowerCase().trim();

  if (needle && isCartNavigationNeedle(needle) && (role === "link" || role === "button")) {
    const cart = findCartNavigationTarget(ranked);
    if (cart) {
      return cart;
    }
  }

  if (needle && isCheckoutNeedle(needle)) {
    const checkout = findCheckoutTarget(ranked);
    if (checkout) {
      return checkout;
    }
  }

  if (elementIndex && elementIndex > 0) {
    const candidate = ranked[elementIndex - 1];
    if (candidate && isElementActionable(candidate)) {
      const candidateRole = inferRole(candidate);
      if (role === candidateRole || (role === "input" && candidateRole === "search")) {
        if (!needle || labelMatchesLoosely(needle, candidate)) {
          return { element: candidate, index: elementIndex };
        }
      }
    }
  }

  if (role === "search" || (role === "input" && needle?.includes("search"))) {
    const searchInput = document.querySelector<HTMLElement>(
      "[data-rf-search-input], input[type=search], input[name=q], [role=searchbox]",
    );
    if (searchInput && isElementActionable(searchInput)) {
      const index = findRankedIndex(ranked, searchInput);
      return { element: searchInput, index: index ?? 1 };
    }
  }

  for (let position = 0; position < ranked.length; position += 1) {
    const candidate = ranked[position];
    const candidateRole = inferRole(candidate);
    if (candidateRole !== role && !(role === "input" && candidateRole === "search")) {
      continue;
    }
    if (needle && !labelMatchesLoosely(needle, candidate)) {
      continue;
    }
    return { element: candidate, index: position + 1 };
  }

  return null;
}

/** Rank click targets using product/listing context — avoids first "Add to cart" on page. */
export function findBySemanticContext(
  matchText: string | undefined,
  role: string = "button",
): DomTargetMatch | null {
  const needle = matchText?.toLowerCase().trim();
  if (!needle) {
    return findByRole(role as "button", undefined, matchText);
  }

  const ranked = collectRankedInteractiveElements();
  const productNeedle = needle
    .replace(/\badd\s+to\s+cart\b/g, "")
    .replace(/\badd\b/g, "")
    .replace(/\bbuy\b/g, "")
    .replace(/\b(?:for|the|to|cart)\b/g, "")
    .trim();
  const productTokens = productNeedle
    .split(/\s+/)
    .filter((token) => token.length > 2);

  let best: { element: HTMLElement; index: number; score: number } | null = null;

  for (let position = 0; position < ranked.length; position += 1) {
    const element = ranked[position];
    if (!isElementActionable(element)) {
      continue;
    }
    const label = elementLabel(element);
    if (!label.includes("add") && role === "button") {
      continue;
    }
    const card = element.closest(
      "[data-rf-product-card], article, [data-testid*='product'], .product-card",
    );
    const cardText = (card?.textContent ?? "").toLowerCase();
    let score = 0;
    if (label.includes(needle) || label.includes(productNeedle)) {
      score += 40;
    }
    if (productNeedle && cardText.includes(productNeedle)) {
      score += 60;
    }
    if (productTokens.length > 0) {
      const matchedTokens = productTokens.filter((token) =>
        cardText.includes(token),
      ).length;
      score += (matchedTokens / productTokens.length) * 60;
    }
    if (inferRole(element) === role || role === "button") {
      score += 10;
    }
    if (score > 0 && (!best || score > best.score)) {
      best = { element, index: position + 1, score };
    }
  }

  if (best) {
    return { element: best.element, index: best.index };
  }
  return findByRole(role as "button", undefined, matchText);
}
