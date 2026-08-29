import type {
  ActionStep,
  PageContext,
  TargetRole,
} from "@/lib/agent/bridge-protocol";
import {
  animateAgentCursorTo,
  clearAgentHighlight,
  elementVisualTarget,
  showAgentHighlight,
} from "@/lib/agent/agent-visual";
import {
  collectRankedInteractiveElements,
  findByRole,
  findBySemanticContext,
  findCartNavigationTarget,
  findCheckoutTarget,
  isElementActionable,
  isTypeableElement,
  isVisible,
} from "@/lib/agent/dom-targeting";
import { agentNavigate } from "@/lib/agent/navigation";
import { extractPageContext } from "@/lib/agent/page-context";
import { attachPageSnapshot } from "@/lib/agent/page-snapshot";
import {
  executionTraceEnabled,
  pushExecutionTrace,
} from "@/lib/agent/execution-trace";
import { extractSearchQuery, sanitizeSearchQuery, searchQuerySatisfied } from "@/lib/search-query";
import { DEMO_BASE, demoRoutes } from "@/lib/demo-routes";

const CHECKOUT_PATH = `${DEMO_BASE}/checkout`;
const SEARCH_PATH = `${DEMO_BASE}/search`;
const CART_PATH = `${DEMO_BASE}/cart`;
const PAGE_CHANGE_TIMEOUT_MS = 10000;
const SEARCH_PAGE_CHANGE_TIMEOUT_MS = 15000;
const PAGE_CHANGE_POLL_MS = 80;
const CURSOR_ANIMATION_MS = 320;
const TYPE_CHAR_DELAY_MS = 42;

export interface StepExecutionResult {
  success: boolean;
  error?: string;
  verified?: boolean;
}

export type ActionProgressCallback = (summary: string) => void;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function cartCount(): number {
  const raw =
    document.querySelector("[data-rf-cart-count]")?.textContent?.trim() ?? "0";
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function recordPageState(): void {
  if (!executionTraceEnabled()) {
    return;
  }
  pushExecutionTrace({
    kind: "page_state",
    page: {
      url: location.href,
      signature: pageSignature(),
      cartCount: cartCount(),
    },
  });
}

function recordTarget(element: HTMLElement, step: ActionStep): void {
  if (!executionTraceEnabled()) {
    return;
  }
  const rect = element.getBoundingClientRect();
  const card = element.closest<HTMLElement>("[data-rf-product-card], article.rf-card");
  pushExecutionTrace({
    kind: "target_resolved",
    step: { action: step.action, matchText: "matchText" in step ? step.matchText : undefined },
    target: {
      tag: element.tagName.toLowerCase(),
      text: (element.textContent ?? "").trim().slice(0, 120),
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      productId: card?.getAttribute("data-rf-product-id") ?? card?.dataset.rfProductId,
    },
  });
}

function recordCursor(point: { x: number; y: number }): void {
  if (!executionTraceEnabled()) {
    return;
  }
  pushExecutionTrace({ kind: "cursor_position", cursor: point });
}

function recordResult(result: StepExecutionResult, step: ActionStep): void {
  if (!executionTraceEnabled()) {
    return;
  }
  pushExecutionTrace({
    kind: "action_result",
    step: { action: step.action },
    result: {
      success: result.success,
      verified: result.verified,
      error: result.error,
    },
  });
  recordPageState();
}

function pageSignature(): string {
  return `${location.href}|${document.title}|${document.querySelectorAll("[data-rf-product-card]").length}|${cartCount()}`;
}

async function waitForUrlMatch(targetUrl: string, timeout = 10000): Promise<boolean> {
  let target: URL;
  try {
    target = new URL(targetUrl, window.location.origin);
  } catch {
    return false;
  }
  const want = target.pathname + target.search + target.hash;
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const current =
      window.location.pathname + window.location.search + window.location.hash;
    if (current === want) {
      return true;
    }
    await sleep(PAGE_CHANGE_POLL_MS);
  }
  const current =
    window.location.pathname + window.location.search + window.location.hash;
  return current === want;
}

async function waitForPageChange(before: string): Promise<boolean> {
  const started = Date.now();
  while (Date.now() - started < PAGE_CHANGE_TIMEOUT_MS) {
    if (pageSignature() !== before) {
      return true;
    }
    await sleep(PAGE_CHANGE_POLL_MS);
  }
  return pageSignature() !== before;
}

function isCartNavigationLabel(needle: string | undefined): boolean {
  if (!needle || needle.includes("add to cart")) {
    return false;
  }
  const normalized = needle.trim().toLowerCase();
  return (
    normalized === "cart" ||
    normalized.startsWith("go to cart") ||
    normalized.startsWith("view cart") ||
    (normalized.includes("cart") && !normalized.includes("add"))
  );
}

function isInViewport(element: HTMLElement): boolean {
  const rect = element.getBoundingClientRect();
  return (
    rect.width > 0 &&
    rect.height > 0 &&
    rect.bottom > 0 &&
    rect.right > 0 &&
    rect.top < window.innerHeight &&
    rect.left < window.innerWidth
  );
}

async function scrollUntilVisible(element: HTMLElement): Promise<void> {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    if (isVisible(element) && isInViewport(element)) {
      return;
    }
    element.scrollIntoView({
      block: "center",
      inline: "center",
      behavior: attempt === 0 ? "instant" : "smooth",
    });
    await sleep(120);
  }
}

function resolveTarget(step: {
  role: TargetRole;
  elementIndex?: number;
  matchText?: string;
}): HTMLElement | null {
  const needle = step.matchText?.toLowerCase().trim();
  const ranked = collectRankedInteractiveElements();

  if (needle && isCartNavigationLabel(needle)) {
    const cart = findCartNavigationTarget(ranked);
    if (cart) {
      return cart.element;
    }
  }

  if (
    needle &&
    (needle.includes("checkout") || needle.includes("sign in to checkout"))
  ) {
    const checkout = findCheckoutTarget(ranked);
    if (checkout) {
      return checkout.element;
    }
  }

  if (
    step.matchText &&
    /add|buy/i.test(step.matchText) &&
    !isCartNavigationLabel(needle)
  ) {
    const semantic = findBySemanticContext(step.matchText, step.role);
    if (semantic) {
      return semantic.element;
    }
  }
  const match = findByRole(step.role, step.elementIndex, step.matchText);
  if (!match || !isElementActionable(match.element)) {
    return null;
  }
  return match.element;
}

async function resolveElementWithScroll(step: {
  role: TargetRole;
  elementIndex?: number;
  matchText?: string;
}): Promise<HTMLElement | null> {
  const element = resolveTarget(step);
  if (!element) {
    return null;
  }
  await scrollUntilVisible(element);
  if (!isElementActionable(element)) {
    return null;
  }
  return element;
}

async function animateToElement(element: HTMLElement): Promise<void> {
  await scrollUntilVisible(element);
  await sleep(50);
  const { rect, point } = elementVisualTarget(element);
  showAgentHighlight(rect);
  recordCursor(point);
  await animateAgentCursorTo(point, CURSOR_ANIMATION_MS);
  await sleep(40);
}

function dispatchClick(element: HTMLElement): void {
  try {
    element.focus({ preventScroll: true });
  } catch {
    // Some elements do not accept focus.
  }
  element.click();
}

function checkoutAuthGateVisible(): boolean {
  const modal = document.querySelector(
    "[data-rf-auth-modal][data-rf-auth-next*='checkout']",
  );
  if (modal && isVisible(modal as HTMLElement)) {
    return true;
  }
  const gate = document.querySelector("[data-rf-checkout-gate], [data-rf-auth-required]");
  return Boolean(gate && isVisible(gate as HTMLElement));
}

function isCheckoutNavigationVerified(targetPath: string): boolean {
  if (location.pathname.startsWith(CHECKOUT_PATH)) {
    return true;
  }
  const params = new URLSearchParams(location.search);
  if (
    params.get("auth") === "login" &&
    (params.get("next") === CHECKOUT_PATH ||
      params.get("next") === encodeURIComponent(CHECKOUT_PATH) ||
      (params.get("next") || "").includes("checkout"))
  ) {
    return true;
  }
  if (targetPath.startsWith(CHECKOUT_PATH) && checkoutAuthGateVisible()) {
    return true;
  }
  return false;
}

async function executeNavigate(url: string): Promise<StepExecutionResult> {
  clearAgentHighlight();
  try {
    const target = new URL(url, window.location.origin);
    const sameOrigin = target.origin === window.location.origin;
    const isSearch = target.pathname.startsWith(SEARCH_PATH);
    const isCheckout = target.pathname.startsWith(CHECKOUT_PATH);

    if (sameOrigin && agentNavigate(url)) {
      const matched = await waitForUrlMatch(url);
      if (matched || (isCheckout && isCheckoutNavigationVerified(target.pathname))) {
        if (isSearch) {
          await waitForStablePage();
        } else {
          await sleep(300);
        }
        return { success: true, verified: true };
      }
    }

    const before = pageSignature();
    window.location.assign(url);
    const matched = await waitForUrlMatch(url, 12000);
    if (matched || (isCheckout && isCheckoutNavigationVerified(target.pathname))) {
      if (isSearch) {
        await waitForStablePage();
      } else {
        await sleep(300);
      }
      return { success: true, verified: true };
    }

    return {
      success: pageSignature() !== before,
      verified: false,
      error: "Navigation did not complete.",
    };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : "Navigation failed.",
    };
  }
}

async function typeTextNaturally(
  element: HTMLInputElement | HTMLTextAreaElement,
  text: string,
): Promise<void> {
  const nativeSetter = Object.getOwnPropertyDescriptor(
    element instanceof HTMLInputElement
      ? HTMLInputElement.prototype
      : HTMLTextAreaElement.prototype,
    "value",
  )?.set;

  element.focus();
  dispatchClick(element);
  await sleep(80);

  if (nativeSetter) {
    nativeSetter.call(element, "");
  } else {
    element.value = "";
  }
  element.dispatchEvent(new Event("input", { bubbles: true }));

  let current = "";
  for (const char of text) {
    current += char;
    if (nativeSetter) {
      nativeSetter.call(element, current);
    } else {
      element.value = current;
    }
    element.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(TYPE_CHAR_DELAY_MS + Math.floor(Math.random() * 18));
  }

  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function submitSearchForm(element: HTMLInputElement): void {
  const submit = element.form?.querySelector<HTMLElement>(
    'button[type="submit"], [data-rf-label="Search"]',
  );
  if (submit) {
    submit.click();
    return;
  }
  element.form?.requestSubmit();
}

function readSearchInputValue(element: HTMLInputElement): string {
  const live = document.querySelector<HTMLInputElement>(
    'input[type="search"][name="q"], [data-rf-search-input]',
  );
  return (live ?? element).value.trim();
}

async function waitForSearchQuery(
  element: HTMLInputElement,
  text: string,
  timeoutMs: number,
): Promise<boolean> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const params = new URLSearchParams(window.location.search);
    const urlQuery = params.get("q") ?? "";
    const inputValue = readSearchInputValue(element);
    if (searchQuerySatisfied(text, urlQuery, inputValue)) {
      return true;
    }
    await sleep(PAGE_CHANGE_POLL_MS);
  }
  return searchQuerySatisfied(
    text,
    new URLSearchParams(window.location.search).get("q") ?? "",
    readSearchInputValue(element),
  );
}

async function executeType(
  step: Extract<ActionStep, { action: "type_in_element" }>,
): Promise<StepExecutionResult> {
  const element = await resolveElementWithScroll(step);
  if (!element || !isTypeableElement(element)) {
    clearAgentHighlight();
    return { success: false, error: "Target is not a text field." };
  }

  const isSearch =
    step.role === "search" ||
    /search/i.test(`${step.matchText ?? ""} ${step.text}`);
  const text = isSearch
    ? sanitizeSearchQuery(step.text) || extractSearchQuery(step.text)
    : step.text.trim();
  if (!text) {
    return {
      success: false,
      error: isSearch
        ? "Search text is empty after sanitization."
        : "Text input is empty.",
    };
  }

  recordTarget(element, step);
  await animateToElement(element);
  await typeTextNaturally(element, text);

  if (isSearch && element instanceof HTMLInputElement) {
    submitSearchForm(element);
  }

  if (!isSearch) {
    clearAgentHighlight();
    return {
      success: true,
      verified: element.value.trim() === text,
    };
  }

  if (
    element instanceof HTMLInputElement &&
    (await waitForSearchQuery(element, text, SEARCH_PAGE_CHANGE_TIMEOUT_MS))
  ) {
    clearAgentHighlight();
    await waitForStablePage();
    return { success: true, verified: true };
  }

  if (element instanceof HTMLInputElement) {
    const target = demoRoutes.searchQuery(text);
    if (agentNavigate(target)) {
      if (await waitForSearchQuery(element, text, 4000)) {
        clearAgentHighlight();
        await waitForStablePage();
        return { success: true, verified: true };
      }
    }
  }

  clearAgentHighlight();
  return {
    success: false,
    verified: false,
    error: "Typed query did not appear in the page.",
  };
}

async function executeClick(
  step: Extract<ActionStep, { action: "click_element" }>,
  onProgress?: ActionProgressCallback,
): Promise<StepExecutionResult> {
  const label = step.matchText ?? "element";
  const isAddToCart = label.toLowerCase().includes("add to cart");
  const isCartNav = isCartNavigationLabel(label.toLowerCase());
  onProgress?.(
    isAddToCart
      ? "Adding to cart…"
      : isCartNav
        ? "Opening cart…"
        : `Clicking ${label}…`,
  );

  const element = await resolveElementWithScroll(step);
  if (!element) {
    clearAgentHighlight();
    return { success: false, error: `Could not find “${label}” to click.` };
  }

  recordTarget(element, step);

  if (element.hasAttribute("disabled") || element.getAttribute("aria-disabled") === "true") {
    clearAgentHighlight();
    return { success: false, error: `“${label}” is not available.` };
  }

  const before = pageSignature();
  const beforeCart = cartCount();
  await animateToElement(element);

  const linkHref =
    element instanceof HTMLAnchorElement && element.href
      ? element.href
      : null;

  if (linkHref && linkHref.startsWith(window.location.origin) && agentNavigate(linkHref)) {
    const targetPath = new URL(linkHref).pathname;
    const isCheckout = targetPath.startsWith(CHECKOUT_PATH);
    const matched = await waitForUrlMatch(linkHref);
    clearAgentHighlight();
    await sleep(200);
    if (matched || (isCheckout && isCheckoutNavigationVerified(targetPath))) {
      return { success: true, verified: true };
    }
    return {
      success: false,
      verified: false,
      error: `Click did not open ${targetPath}.`,
    };
  }

  dispatchClick(element);

  if (isAddToCart || element.hasAttribute("data-rf-add-to-cart")) {
    const started = Date.now();
    while (Date.now() - started < 3500) {
      if (cartCount() > beforeCart) {
        clearAgentHighlight();
        await sleep(250);
        return { success: true, verified: true };
      }
      await sleep(PAGE_CHANGE_POLL_MS);
    }
    clearAgentHighlight();
    return {
      success: false,
      error: "Cart count did not increase after add to cart.",
    };
  }

  if (linkHref && linkHref.startsWith(window.location.origin)) {
    const targetPath = new URL(linkHref).pathname;
    const isCheckout = targetPath.startsWith(CHECKOUT_PATH);
    const matched = await waitForUrlMatch(linkHref);
    clearAgentHighlight();
    if (matched || (isCheckout && isCheckoutNavigationVerified(targetPath))) {
      await sleep(200);
      return { success: true, verified: true };
    }
    return {
      success: false,
      verified: false,
      error: `Click did not open ${targetPath}.`,
    };
  } else {
    await waitForPageChange(before);
  }

  clearAgentHighlight();
  await sleep(200);
  return { success: true, verified: true };
}

export async function executeActionStep(
  step: ActionStep,
  onProgress?: ActionProgressCallback,
): Promise<StepExecutionResult> {
  if (executionTraceEnabled()) {
    pushExecutionTrace({
      kind: "action_start",
      step: step as unknown as Record<string, unknown>,
    });
    recordPageState();
  }

  let result: StepExecutionResult;
  if (step.action === "wait_for_user" || step.action === "ready_for_payment_link") {
    clearAgentHighlight();
    result = { success: true, verified: true };
  } else if (step.action === "navigate_url") {
    onProgress?.("Opening search results…");
    result = await executeNavigate(step.url);
  } else if (step.action === "set_state") {
    result = { success: true, verified: true };
  } else if (step.action === "click_element") {
    result = await executeClick(step, onProgress);
  } else if (step.action === "type_in_element") {
    const isSearch =
      step.role === "search" ||
      /search/i.test(`${step.matchText ?? ""} ${step.text}`);
    const query = isSearch
      ? sanitizeSearchQuery(step.text) || extractSearchQuery(step.text)
      : step.text;
    onProgress?.(
      isSearch
        ? `Searching for ${query || step.text}…`
        : `Entering text in ${step.matchText || "the field"}…`,
    );
    result = await executeType(step);
  } else if (step.action === "highlight_element") {
    const element = await resolveElementWithScroll(step);
    if (!element) {
      result = { success: false, error: "Could not find element to highlight." };
    } else {
      await animateToElement(element);
      await sleep(500);
      clearAgentHighlight();
      result = { success: true, verified: true };
    }
  } else if (step.action === "scroll_page") {
    const amount = step.amountPx ?? 600;
    if (step.direction === "top") {
      window.scrollTo(0, 0);
    } else if (step.direction === "bottom") {
      window.scrollTo(0, document.documentElement.scrollHeight);
    } else if (step.direction === "up") {
      window.scrollBy(0, -amount);
    } else {
      window.scrollBy(0, amount);
    }
    result = { success: true, verified: true };
  } else if (step.action === "wait") {
    await sleep(step.durationMs ?? 300);
    result = { success: true, verified: true };
  } else if (step.action === "go_back") {
    window.history.back();
    result = { success: true, verified: true };
  } else {
    clearAgentHighlight();
    result = { success: false, error: `Unsupported action: ${(step as ActionStep).action}` };
  }

  recordResult(result, step);
  return result;
}

export async function waitForStablePage(): Promise<PageContext> {
  const deadline = Date.now() + 9000;
  let lastCount = -1;
  let stablePasses = 0;

  while (Date.now() < deadline) {
    await sleep(150);
    const ctx = extractPageContext();
    let path = "/";
    try {
      path = new URL(ctx.url).pathname;
    } catch {
      path = window.location.pathname;
    }

    if (path.startsWith(SEARCH_PATH)) {
      if (ctx.products.length > 0) {
        if (ctx.products.length === lastCount) {
          stablePasses += 1;
        } else {
          stablePasses = 0;
          lastCount = ctx.products.length;
        }
        if (stablePasses >= 2) {
          return await attachPageSnapshot(ctx);
        }
      }
      continue;
    }
    if (path.startsWith(CART_PATH) && ctx.elements.length > 0) {
      return await attachPageSnapshot(ctx);
    }
    if (
      path.startsWith(CHECKOUT_PATH) ||
      path.startsWith(`${DEMO_BASE}/product/`)
    ) {
      return await attachPageSnapshot(ctx);
    }
    if ((path === DEMO_BASE || path === `${DEMO_BASE}/`) && ctx.elements.length > 5) {
      return await attachPageSnapshot(ctx);
    }
  }
  return await attachPageSnapshot(extractPageContext());
}
